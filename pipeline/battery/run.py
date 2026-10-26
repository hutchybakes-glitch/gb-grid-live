"""Run the battery pipeline end to end and write the Power BI files to ``data/battery``.

    python -m pipeline.battery.run              # fetch what's new, forecast, optimise, export
    python -m pipeline.battery.run --no-fetch   # rebuild from the saved state only (no API calls)

Steps: update state (prices, forecasts, carbon) -> fit the tariff formula -> price forecasts (backtest
for past days, live for the day being planned) -> optimiser for every day x region x battery type ->
plans for the planned day and the last settled day -> export CSVs. Never overwrites good data with an
empty fetch; a failed step keeps the previous files.
"""
from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from pipeline.battery import forecast, optimise, settings, sources, store, tariff

log = logging.getLogger("pipeline.battery")

CONFIGS = [(h, e) for h in settings.HOURS_OPTIONS for e in settings.EFFICIENCY_OPTIONS]
REGION_CODES = [*settings.REGIONS, settings.WHOLESALE_CODE]


# ---------------------------------------------------------------- state
def update_state(now: datetime) -> None:
    """Fetch every day not yet held (plus the most recent days) for each source."""
    today = now.astimezone(settings.UK).date()
    tomorrow = today + timedelta(days=1)
    client = sources.elexon_client()
    jobs = [
        ("prices", sources.market_index, today),
        ("wind_solar", sources.wind_solar_forecast, tomorrow),
        ("demand", sources.demand_forecast, tomorrow),
        ("carbon", sources.carbon_intensity, tomorrow),
    ]
    try:
        for name, fetch, last in jobs:
            old = store.load(name)
            days = store.days_to_fetch(old, settings.HISTORY_START, last)
            log.info("%s: fetching %d days", name, len(days))
            new_frames = [fetch(client, a, b) for a, b in store.runs(days)]
            new = pd.concat([f for f in new_frames if not f.empty]) if any(not f.empty for f in new_frames) else old.iloc[:0]
            store.save(name, store.merge(name, old, new))
    finally:
        client.close()


def fit_tariffs(now: datetime) -> pd.DataFrame:
    """Refit the tariff formula per region on the last 28 days; keep the previous fit if a region fails."""
    path = settings.OUT_DIR / "tariff_regions.csv"
    previous = pd.read_csv(path).set_index("RegionCode") if path.exists() else None
    prices = store.load("prices")
    last = now.astimezone(settings.UK).date() - timedelta(days=1)
    first = last - timedelta(days=settings.TARIFF_FIT_DAYS - 1)
    client = sources.elexon_client()
    rows = []
    try:
        for code, name in settings.REGIONS.items():
            fit = None
            try:
                fit = tariff.fit(code, sources.agile_prices(client, code, first, last), prices)
            except Exception as exc:  # one region failing must not lose the others
                log.warning("Tariff fit failed for %s: %s", code, exc)
            if fit is not None:
                rows.append({"RegionCode": code, "RegionName": name, **_tile(code), "Multiplier": fit.multiplier,
                             "PeakCharge": fit.peak_charge, "FitErrorP": fit.error_p,
                             "FitCorrelation": fit.correlation, "FitDays": fit.days, "FitEnd": fit.fit_end})
            elif previous is not None and code in previous.index:
                rows.append({"RegionCode": code, **previous.loc[code].to_dict()})
            else:
                raise RuntimeError(f"No tariff fit for region {code} and no previous fit to fall back on")
    finally:
        client.close()
    rows.append({"RegionCode": settings.WHOLESALE_CODE, "RegionName": "Wholesale market (no tariff)", **_tile(settings.WHOLESALE_CODE),
                 "Multiplier": 1.0, "PeakCharge": 0.0, "FitErrorP": 0.0, "FitCorrelation": 1.0,
                 "FitDays": 0, "FitEnd": ""})
    return pd.DataFrame(rows).set_index("RegionCode")


def _tile(code: str) -> dict:
    """Tile-map position and short label, matching the GB Grid Live website's map."""
    col, row, abbr = settings.TILES.get(code, (-1, -1, "Wholesale"))
    return {"TileCol": col, "TileRow": row, "ShortName": abbr}


# ---------------------------------------------------------------- half-hours and forecasts
def half_hour_frame(last_day: date) -> pd.DataFrame:
    """Every half-hour from the start of history to the end of ``last_day``, with all inputs joined on."""
    start, _ = sources.local_day_bounds(settings.HISTORY_START)
    _, end = sources.local_day_bounds(last_day)
    df = pd.DataFrame({"period_start_utc": pd.date_range(start, end, freq="30min", inclusive="left", tz="UTC")})
    for name in ("prices", "wind_solar", "demand", "carbon"):
        df = df.merge(store.load(name), on="period_start_utc", how="left")
    return df


def update_forecasts(feat: pd.DataFrame, plan_day: date, now: datetime) -> pd.DataFrame:
    """Fill in forecasts for days that have none. A forecast, once made, is never changed."""
    held = store.load("forecasts")
    have = store.local_days(held)
    days = sorted(d for d in set(feat["local_date"]) if settings.BACKTEST_START <= d <= plan_day and d not in have)
    if not days:
        return held
    new_parts = []
    past = [d for d in days if d < plan_day - timedelta(days=1)]
    if past:
        pred = forecast.backtest(feat, past[0], past[-1])
        pred = pred[feat.loc[pred.index, "local_date"].isin(past)]
        new_parts.append(pd.DataFrame({"period_start_utc": feat.loc[pred.index, "period_start_utc"],
                                       "forecast": pred.round(2), "made_utc": "backtest",
                                       "model": forecast.MODEL_VERSION}))
    for d in (x for x in days if x >= plan_day - timedelta(days=1)):
        pred = forecast.forecast_day(feat, d)
        if pred.empty:
            log.warning("No forecast for %s: inputs incomplete", d)
            continue
        new_parts.append(pd.DataFrame({"period_start_utc": feat.loc[pred.index, "period_start_utc"],
                                       "forecast": pred.round(2), "made_utc": now.strftime("%Y-%m-%dT%H:%MZ"),
                                       "model": forecast.MODEL_VERSION}))
    if new_parts:
        held = store.merge("forecasts", held, pd.concat(new_parts))
        store.save("forecasts", held)
    return held


# ---------------------------------------------------------------- optimiser
def _day_results(args: tuple) -> list[dict]:
    """All strategies for one day, every region and battery type (runs in a worker process)."""
    day, period_start, price, fc, base, carbon, local_hour, fits = args
    peak = tariff.is_peak(pd.Series(period_start))
    out = []
    for region in REGION_CODES:
        actual = tariff.region_prices_gbp_per_kwh(price, peak, region, fits)
        planned = tariff.region_prices_gbp_per_kwh(fc, peak, region, fits) if fc is not None else None
        naive = tariff.region_prices_gbp_per_kwh(base, peak, region, fits) if base is not None else None
        for hours, eff in CONFIGS:
            strategies = {
                "Hindsight": optimise.best_schedule(actual, hours, eff),
                "Timer": optimise.timer_schedule(local_hour, hours, eff),
            }
            if planned is not None:
                strategies["Forecast"] = optimise.best_schedule(planned, hours, eff)
            if naive is not None:
                # The yardstick for the forecast: plan on last week's prices for the same half-hours.
                strategies["LastWeek"] = optimise.best_schedule(naive, hours, eff)
            for name, sched in strategies.items():
                r = optimise.settle(sched, actual, carbon)
                out.append({"SettlementDate": day.isoformat(), "RegionCode": region, "Hours": hours,
                            "Efficiency": eff, "Strategy": name, **{k: round(v, 5) for k, v in r.items()}})
    return out


def _day_inputs(feat: pd.DataFrame, fits: pd.DataFrame, days: list[date]) -> list[tuple]:
    """Arrays per day for the workers; a day needs every actual price to be settled."""
    jobs = []
    for d, g in feat[feat["local_date"].isin(days)].groupby("local_date"):
        if g["price"].isna().any():
            continue
        fc = g["forecast"].to_numpy() if g["forecast"].notna().all() else None
        # Last week's prices; where that week has gaps, the week before (what an operator would plan on), so the
        # LastWeek strategy covers the same days as the others.
        week = g["lag_7d"].fillna(g["lag_14d"])
        base = week.to_numpy() if week.notna().all() else None
        local_hour = g["period_start_utc"].dt.tz_convert(settings.UK).dt.hour.to_numpy()
        jobs.append((d, g["period_start_utc"].to_numpy(), g["price"].to_numpy(), fc, base,
                     g["carbon"].to_numpy(dtype=float), local_hour, fits))
    return jobs


def update_results(feat: pd.DataFrame, fits: pd.DataFrame, last_settled: date, workers: int) -> pd.DataFrame:
    """Optimiser results for days not yet held, plus recent days (tariff refits and late prices)."""
    path = settings.OUT_DIR / "daily_results.csv"
    held = pd.read_csv(path, dtype={"RegionCode": str}) if path.exists() else pd.DataFrame()
    have = set(pd.to_datetime(held["SettlementDate"]).dt.date) if not held.empty else set()
    recent = last_settled - timedelta(days=settings.REFETCH_RECENT_DAYS - 1)
    days = [d for d in pd.date_range(settings.RESULTS_START, last_settled).date if d not in have or d >= recent]
    jobs = _day_inputs(feat, fits, days)
    log.info("Optimiser: %d days x %d regions x %d battery types", len(jobs), len(REGION_CODES), len(CONFIGS))
    rows: list[dict] = []
    if workers > 1 and len(jobs) > 4:
        with ProcessPoolExecutor(workers) as pool:
            for part in pool.map(_day_results, jobs, chunksize=4):
                rows.extend(part)
    else:
        for job in jobs:
            rows.extend(_day_results(job))
    new = pd.DataFrame(rows)
    if new.empty:
        return held
    done = set(new["SettlementDate"])
    keep = held[~held["SettlementDate"].isin(done)] if not held.empty else held
    return pd.concat([keep, new]).sort_values(["SettlementDate", "RegionCode", "Hours", "Efficiency", "Strategy"])


def plans(feat: pd.DataFrame, fits: pd.DataFrame, plan_day: date, last_settled: date) -> pd.DataFrame:
    """Half-hourly schedules: the planned day (forecast) and the last settled day (forecast and hindsight)."""
    rows = []
    for day, kinds in ((plan_day, ("Forecast",)), (last_settled, ("Forecast", "Hindsight"))):
        g = feat[feat["local_date"] == day]
        if g.empty:
            continue
        peak = tariff.is_peak(g["period_start_utc"])
        keys = g["period_start_utc"].dt.strftime("%Y-%m-%dT%H:%M").to_numpy()
        for kind in kinds:
            series = g["forecast"] if kind == "Forecast" else g["price"]
            if series.isna().any():
                continue
            for region in REGION_CODES:
                p = tariff.region_prices_gbp_per_kwh(series.to_numpy(), peak, region, fits)
                for hours, eff in CONFIGS:
                    s = optimise.best_schedule(p, hours, eff)
                    net = s.charge - s.use
                    action = np.where(net > 1e-6, "Charge", np.where(net < -1e-6, "Use", "Hold"))
                    rows.append(pd.DataFrame({
                        "PlanDate": day.isoformat(), "Strategy": kind, "PeriodStartUTC": keys,
                        "RegionCode": region, "Hours": hours, "Efficiency": eff, "Action": action,
                        "PowerPerKWh": np.round(net, 4), "ChargeLevel": np.round(s.level, 4),
                    }))
    return pd.concat(rows) if rows else pd.DataFrame()


def _windows(local_times: list[str], active: np.ndarray) -> str:
    """Turn half-hours that are active into plain-English time windows, e.g. '00:30-04:00, 13:00-14:00'."""
    out, start = [], None
    for i, on in enumerate(active):
        if on and start is None:
            start = i
        if start is not None and (not on or i == len(active) - 1):
            end = i if on else i - 1
            h, m = map(int, local_times[end].split(":"))
            finish = f"{(h + (m + 30) // 60) % 24:02d}:{(m + 30) % 60:02d}"
            out.append(f"{local_times[start]}–{finish}")
            start = None
    return ", ".join(out)


def plan_summary(feat: pd.DataFrame, fits: pd.DataFrame, plan_day: date, last_settled: date) -> pd.DataFrame:
    """One row per day x strategy x region x battery type: the windows in words and the money expected and made."""
    rows = []
    for day, kinds in ((plan_day, ("Forecast",)), (last_settled, ("Forecast", "Hindsight"))):
        g = feat[feat["local_date"] == day]
        if g.empty:
            continue
        peak = tariff.is_peak(g["period_start_utc"])
        times = g["period_start_utc"].dt.tz_convert(settings.UK).dt.strftime("%H:%M").tolist()
        carbon = g["carbon"].to_numpy(dtype=float)
        for kind in kinds:
            series = g["forecast"] if kind == "Forecast" else g["price"]
            if series.isna().any():
                continue
            for region in REGION_CODES:
                believed = tariff.region_prices_gbp_per_kwh(series.to_numpy(), peak, region, fits)
                actual = (tariff.region_prices_gbp_per_kwh(g["price"].to_numpy(), peak, region, fits)
                          if g["price"].notna().all() else None)
                for hours, eff in CONFIGS:
                    s = optimise.best_schedule(believed, hours, eff)
                    expected = optimise.settle(s, believed, carbon)
                    settled = optimise.settle(s, actual, carbon) if actual is not None else None
                    rows.append({
                        "PlanDate": day.isoformat(), "Strategy": kind, "RegionCode": region, "Hours": hours,
                        "Efficiency": eff,
                        "ChargeWindows": _windows(times, s.charge > 1e-6),
                        "UseWindows": _windows(times, s.use > 1e-6),
                        "ExpectedSavingPerKWh": round(expected["SavingPerKWh"], 5),
                        "ExpectedChargeCostPerKWh": round(expected["ChargeCostPerKWh"], 5),
                        "ExpectedUseValuePerKWh": round(expected["UseValuePerKWh"], 5),
                        "SettledSavingPerKWh": round(settled["SavingPerKWh"], 5) if settled else None,
                        "CarbonKgPerKWh": round(expected["CarbonKgPerKWh"], 5),
                    })
    return pd.DataFrame(rows)


def daily_prices(feat: pd.DataFrame) -> pd.DataFrame:
    """One row per day: price summary and the day's prices packed into text, for the price calendar."""
    df = feat[feat["price"].notna()].copy()
    df["slot"] = df["slot"].astype(int)

    def per_day(g: pd.DataFrame) -> pd.Series:
        p = np.sort(g["price"].to_numpy())
        k = min(8, len(p) // 2)
        return pd.Series({
            "AvgPrice": round(float(g["price"].mean()), 2),
            "MinPrice": round(float(p[0]), 2),
            "MaxPrice": round(float(p[-1]), 2),
            "Spread4hGBP": round(float(p[-k:].mean() - p[:k].mean()), 2),
            "NegativeHalfHours": int((g["price"] < 0).sum()),
            "AvgLeftoverMW": round(float((g["demand_mw"] - g["wind_mw"]).mean()), 0) if g["demand_mw"].notna().any() else None,
            "AvgWindMW": round(float(g["wind_mw"].mean()), 0) if g["wind_mw"].notna().any() else None,
            # slot:price pairs, so repeated or skipped hours on clock-change days stay unambiguous
            "PricesPacked": "|".join(f"{s}:{round(v)}" for s, v in zip(g["slot"], g["price"])),
        })

    out = df.groupby("local_date").apply(per_day, include_groups=False).reset_index()
    return out.rename(columns={"local_date": "SettlementDate"})


# ---------------------------------------------------------------- export
def export_half_hours(feat: pd.DataFrame, plan_day: date, review_day: date) -> pd.DataFrame:
    """The half-hour table Power BI reads (UK local fields added here so Power BI never converts zones)."""
    local = feat["period_start_utc"].dt.tz_convert(settings.UK)
    out = pd.DataFrame({
        "PeriodStartUTC": feat["period_start_utc"].dt.strftime("%Y-%m-%dT%H:%M"),
        "SettlementDate": feat["local_date"].astype(str),
        "SettlementPeriod": feat.groupby("local_date").cumcount() + 1,
        "LocalTime": local.dt.strftime("%H:%M"),
        "ZoneLabel": np.where(local.map(lambda t: bool(t.dst())), "BST", "GMT"),
        "WholesalePrice": feat["price"].round(2),
        "ForecastPrice": feat["forecast"].round(2),
        "BaselinePrice": feat["lag_7d"].round(2),
        "DemandFcMW": feat["demand_mw"].round(0).astype("Int64"),
        "WindFcMW": feat["wind_mw"].round(0).astype("Int64"),
        "SolarFcMW": feat["solar_mw"].round(0).astype("Int64"),
        # Demand the wind and sun can't cover. National demand (NDF) already excludes rooftop and other embedded
        # solar, which shows up as lower demand, so only wind is taken off; subtracting solar again counted it twice.
        "LeftoverMW": (feat["demand_mw"] - feat["wind_mw"]).round(0).astype("Int64"),
        "CarbonIntensity": feat["carbon"].round(0).astype("Int64"),
        "IsPlanDay": (feat["local_date"] == plan_day).astype(int),
        # The last fully priced day, reviewed on the plan page ("how yesterday's plan did")
        "IsReviewDay": (feat["local_date"] == review_day).astype(int),
    })
    return out


def _uk_text(ts: datetime | pd.Timestamp) -> str:
    """A UTC moment as UK local text, e.g. '26 Oct 17:30'."""
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(settings.UK).strftime("%d %b %H:%M").lstrip("0")


def write_csv(df: pd.DataFrame, name: str) -> None:
    """Write one published file (Windows-safe newlines)."""
    settings.OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(settings.OUT_DIR / name, index=False, lineterminator="\n")


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-fetch", action="store_true", help="use saved state only")
    parser.add_argument("--workers", type=int, default=4, help="processes for the optimiser backfill")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    now = datetime.now(timezone.utc)
    today = now.astimezone(settings.UK).date()

    if not args.no_fetch:
        update_state(now)
        fits = fit_tariffs(now)
        write_csv(fits.reset_index(), "tariff_regions.csv")
    fits = pd.read_csv(settings.OUT_DIR / "tariff_regions.csv").set_index("RegionCode")

    tomorrow = today + timedelta(days=1)
    hh = half_hour_frame(tomorrow)
    tomorrow_rows = hh[hh["period_start_utc"].dt.tz_convert(settings.UK).dt.date == tomorrow]
    # Plan tomorrow once its wind/solar forecast is out (16:45 UTC); until then the plan is for today.
    plan_day = tomorrow if tomorrow_rows["wind_mw"].notna().all() and tomorrow_rows["demand_mw"].notna().all() else today
    if plan_day == today:
        hh = hh[hh["period_start_utc"].dt.tz_convert(settings.UK).dt.date <= today]

    feat = forecast.build_features(hh)
    fc = update_forecasts(feat, plan_day, now)
    feat = feat.merge(fc[["period_start_utc", "forecast"]], on="period_start_utc", how="left")

    complete = feat.groupby("local_date")["price"].apply(lambda s: s.notna().all())
    last_settled = max(d for d, ok in complete.items() if ok)

    results = update_results(feat, fits, last_settled, args.workers)
    write_csv(results, "daily_results.csv")
    write_csv(plans(feat, fits, plan_day, last_settled), "plans.csv")
    write_csv(plan_summary(feat, fits, plan_day, last_settled), "plan_summary.csv")
    prices_daily = daily_prices(feat)
    # Flag the 12 months up to the last settled day, so the price calendar's filter never depends on "today"
    prices_daily["InLastYear"] = (prices_daily["SettlementDate"] > last_settled - timedelta(days=365)).astype(int)
    write_csv(prices_daily, "daily_prices.csv")
    write_csv(forecast.accuracy(feat[feat["local_date"] >= settings.BACKTEST_START]), "forecast_accuracy.csv")
    write_csv(export_half_hours(feat, plan_day, last_settled), "half_hours.csv")

    plan_made = fc.loc[fc["period_start_utc"].dt.tz_convert(settings.UK).dt.date == plan_day, "made_utc"]
    hist = feat[feat["local_date"] >= settings.HISTORY_START]
    meta = pd.DataFrame([{
        "RunUTC": now.strftime("%Y-%m-%dT%H:%MZ"),
        "NewestPriceUTC": feat.loc[feat["price"].notna(), "period_start_utc"].max().strftime("%Y-%m-%dT%H:%MZ"),
        "LastSettledDate": last_settled.isoformat(),
        "PlanDate": plan_day.isoformat(),
        "ForecastMadeUTC": plan_made.iloc[0] if len(plan_made) else "",
        "ModelVersion": forecast.MODEL_VERSION,
        # The same moments in UK local time as plain text, so Power BI never converts zones
        "RunLocal": _uk_text(now),
        "NewestPriceLocal": _uk_text(feat.loc[feat["price"].notna(), "period_start_utc"].max() + pd.Timedelta(minutes=30)),
        "ForecastMadeLocal": _uk_text(pd.Timestamp(plan_made.iloc[0])) if len(plan_made) and plan_made.iloc[0] != "backtest" else "",
        "MissingPriceHalfHours": int(hist.loc[hist["local_date"] <= last_settled, "price"].isna().sum()),
        "MissingForecastHalfHours": int(hist.loc[hist["local_date"] >= settings.BACKTEST_START, "forecast"].isna().sum()),
    }])
    write_csv(meta, "pipeline_meta.csv")
    log.info("Done: plan day %s, last settled %s, %d result rows", plan_day, last_settled, len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
