"""Fetchers for the battery pipeline. Each returns a tidy DataFrame keyed by half-hour start in UTC.

Elexon (wholesale prices, day-ahead wind/solar and demand forecasts) and the Carbon Intensity API are
openly licensed and published. Octopus Agile prices are fetched only to calibrate the tariff formula;
its terms don't allow republishing them, so they never leave this process.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from pipeline import config
from pipeline.battery import settings
from pipeline.http import ApiClient

log = logging.getLogger(__name__)


def _iso(ts: datetime) -> str:
    """Format a UTC datetime the way Elexon and Octopus expect (minute precision, Z suffix)."""
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    """UTC start and end of a UK local day (23, 24 or 25 hours long)."""
    start = datetime.combine(day, datetime.min.time(), settings.UK).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), settings.UK).astimezone(timezone.utc)
    return start, end


def decision_cutoff(day: date) -> datetime:
    """The latest moment information may be used to plan ``day``: 17:15 UTC the day before."""
    return datetime.combine(day - timedelta(days=1), settings.DECISION_TIME_UTC, timezone.utc)


def market_index(client: ApiClient, first: date, last: date) -> pd.DataFrame:
    """Actual wholesale price (APX market index, £/MWh) for UK local days ``first``..``last``."""
    start, _ = local_day_bounds(first)
    _, end = local_day_bounds(last)
    frames = []
    a = start
    while a < end:
        # The route rejects windows over 7 days, and treats ``to`` as inclusive.
        b = min(a + timedelta(days=settings.MARKET_INDEX_MAX_DAYS), end)
        body = client.get_json(
            "balancing/pricing/market-index",
            {"from": _iso(a), "to": _iso(b - timedelta(minutes=1)), "format": "json"},
        )
        rows = [r for r in body["data"] if r["dataProvider"] == "APXMIDP"]
        if rows:
            frames.append(pd.DataFrame({
                "period_start_utc": pd.to_datetime([r["startTime"] for r in rows], utc=True),
                "price": [float(r["price"]) for r in rows],
                # Zero volume means no trades: the 0 price is a placeholder, not a real price.
                "volume": [float(r["volume"]) for r in rows],
            }))
        a = b
    if not frames:
        return pd.DataFrame(columns=["period_start_utc", "price"])
    df = pd.concat(frames).drop_duplicates("period_start_utc", keep="last")
    df = df[df["volume"] > 0]
    return df[["period_start_utc", "price"]].sort_values("period_start_utc").reset_index(drop=True)


def wind_solar_forecast(client: ApiClient, first: date, last: date) -> pd.DataFrame:
    """Day-ahead wind and solar forecast (MW) as known at each day's decision time."""
    frames = []
    # The route groups by UTC day, so in BST the first hour of a UK day sits in the previous UTC day.
    d = first - timedelta(days=1)
    while d <= last:
        e = min(d + timedelta(days=settings.DGWS_CHUNK_DAYS - 1), last)
        body = client.get_json(
            "forecast/generation/wind-and-solar/day-ahead",
            # ``to`` must be after ``from`` or only one period comes back; extra rows are trimmed below.
            {"from": d.isoformat(), "to": (e + timedelta(days=1)).isoformat(),
             "processType": "day ahead", "format": "json"},
        )
        if body["data"]:
            frames.append(pd.DataFrame(body["data"]))
        d = e + timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=["period_start_utc", "wind_mw", "solar_mw"])
    raw = pd.concat(frames)
    raw["period_start_utc"] = pd.to_datetime(raw["startTime"], utc=True)
    raw["publish_utc"] = pd.to_datetime(raw["publishTime"], utc=True)
    # Each request also returns the first half-hour of the next chunk, so the same row arrives twice at chunk
    # boundaries; without this the wind and solar for those half-hours were summed twice (found in review).
    raw = raw.drop_duplicates(["period_start_utc", "psrType", "publish_utc"])
    raw = _keep_known_at_decision(raw)
    raw["kind"] = raw["psrType"].map({"Solar": "solar_mw", "Wind Offshore": "wind_mw", "Wind Onshore": "wind_mw"})
    wide = raw.groupby(["period_start_utc", "kind"])["quantity"].sum().unstack("kind").reset_index()
    return _trim_to_days(wide, first, last)


def demand_forecast(client: ApiClient, first: date, last: date) -> pd.DataFrame:
    """Day-ahead national demand forecast (MW) as known at each day's decision time."""
    frames = []
    d = first
    while d <= last:
        cutoff = decision_cutoff(d)
        # Publications are listed by publish time, at most one day per call: ask for the day before up to the cutoff.
        body = client.get_json(
            "datasets/NDF",
            {"publishDateTimeFrom": _iso(cutoff.replace(hour=0, minute=0)),
             "publishDateTimeTo": _iso(cutoff), "format": "json"},
        )
        if body["data"]:
            frames.append(pd.DataFrame(body["data"]))
        d += timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=["period_start_utc", "demand_mw"])
    raw = pd.concat(frames)
    raw["period_start_utc"] = pd.to_datetime(raw["startTime"], utc=True)
    raw["publish_utc"] = pd.to_datetime(raw["publishTime"], utc=True)
    raw = _keep_known_at_decision(raw)
    out = raw.groupby("period_start_utc", as_index=False)["demand"].last().rename(columns={"demand": "demand_mw"})
    return _trim_to_days(out, first, last)


def carbon_intensity(client: ApiClient, first: date, last: date) -> pd.DataFrame:
    """National carbon intensity (gCO2/kWh): actual where published, otherwise the forecast."""
    frames = []
    d = first
    while d <= last:
        e = min(d + timedelta(days=settings.CARBON_CHUNK_DAYS - 1), last)
        a, _ = local_day_bounds(d)
        _, b = local_day_bounds(e)
        # ``{from}`` returns the period *ending* at from, so start 30 minutes later to get periods starting at a.
        path = f"https://api.carbonintensity.org.uk/intensity/{_iso(a + timedelta(minutes=30))}/{_iso(b)}"
        body = client.get_json(path)
        rows = body.get("data", [])
        if rows:
            frames.append(pd.DataFrame({
                "period_start_utc": pd.to_datetime([r["from"] for r in rows], utc=True),
                "carbon": [r["intensity"]["actual"] if r["intensity"]["actual"] is not None
                           else r["intensity"]["forecast"] for r in rows],
            }))
        d = e + timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=["period_start_utc", "carbon"])
    out = pd.concat(frames).dropna().drop_duplicates("period_start_utc", keep="last")
    return _trim_to_days(out, first, last)


def agile_prices(client: ApiClient, region: str, first: date, last: date) -> pd.DataFrame:
    """Dynamic tariff prices for one region, for calibration only (never written to the published files)."""
    start, _ = local_day_bounds(first)
    _, end = local_day_bounds(last)
    tariff = f"E-1R-{settings.AGILE_PRODUCT}-{region}"
    body = client.get_json(
        f"{settings.OCTOPUS_BASE_URL}/products/{settings.AGILE_PRODUCT}/electricity-tariffs/{tariff}/standard-unit-rates/",
        {"page_size": "1500", "period_from": _iso(start), "period_to": _iso(end)},
    )
    rows = body.get("results", [])
    return pd.DataFrame({
        "period_start_utc": pd.to_datetime([r["valid_from"] for r in rows], utc=True),
        "exc_vat": [float(r["value_exc_vat"]) for r in rows],
        "inc_vat": [float(r["value_inc_vat"]) for r in rows],
    })


def _keep_known_at_decision(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep, for each half-hour, only rows published before that day's decision time.

    This is what makes the backtest honest: the planner never sees a forecast it couldn't have had.
    """
    local_day = raw["period_start_utc"].dt.tz_convert(settings.UK).dt.date
    cutoff = local_day.map(lambda d: pd.Timestamp(decision_cutoff(d)))
    known = raw[raw["publish_utc"] <= cutoff].copy()
    # Of what was known, the latest publication wins.
    latest = known.groupby("period_start_utc")["publish_utc"].transform("max")
    return known[known["publish_utc"] == latest]


def _trim_to_days(df: pd.DataFrame, first: date, last: date) -> pd.DataFrame:
    """Keep only half-hours that fall in UK local days ``first``..``last``."""
    start, _ = local_day_bounds(first)
    _, end = local_day_bounds(last)
    mask = (df["period_start_utc"] >= start) & (df["period_start_utc"] < end)
    return df[mask].sort_values("period_start_utc").reset_index(drop=True)


def elexon_client() -> ApiClient:
    """A polite client for Elexon (one request a second, retries with backoff)."""
    return ApiClient(settings.ELEXON_BASE_URL)


__all__ = [
    "market_index", "wind_solar_forecast", "demand_forecast", "carbon_intensity", "agile_prices",
    "local_day_bounds", "decision_cutoff", "elexon_client", "config",
]
