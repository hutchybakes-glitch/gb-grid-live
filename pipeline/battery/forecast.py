"""Tomorrow's wholesale price forecast, from tomorrow's wind, solar and demand forecasts.

There is no free source of tomorrow's GB wholesale price, so the planner needs a forecast. Every input is
something that was published before 17:15 UTC the day before (see ``sources.decision_cutoff``), and the
backtest retrains month by month on earlier data only, so its error is the error a real user would have had.
The yardstick is a naive baseline: the same half-hour one week earlier.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import lightgbm as lgb
import numpy as np
import pandas as pd

from pipeline.battery import settings

log = logging.getLogger(__name__)

MODEL_VERSION = "lgbm-v1"
FEATURES = [
    "leftover_mw", "demand_mw", "wind_mw", "solar_mw", "slot", "dow", "month",
    "level_7d", "lag_2d", "lag_7d",
]
PARAMS = {
    "objective": "regression", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 40,
    "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1, "seed": 7,
}
ROUNDS = 400


def build_features(hh: pd.DataFrame) -> pd.DataFrame:
    """Add model inputs to the half-hour frame. Uses only what was known at the decision time.

    Expects columns period_start_utc, price, wind_mw, solar_mw, demand_mw.
    """
    df = hh.copy()
    local = df["period_start_utc"].dt.tz_convert(settings.UK)
    df["local_date"] = local.dt.date
    # Slot = local half-hour of the day (0-47); on clock-change days the repeated or skipped hour shares slots.
    df["slot"] = local.dt.hour * 2 + local.dt.minute // 30
    df["dow"] = local.dt.dayofweek
    df["month"] = local.dt.month
    df["leftover_mw"] = df["demand_mw"] - df["wind_mw"] - df["solar_mw"]

    # Lags by local day and slot: D-2 is the latest whole day known at 17:15 on D-1.
    by_key = df.groupby(["local_date", "slot"])["price"].mean()
    for days, name in ((2, "lag_2d"), (7, "lag_7d")):
        key = pd.MultiIndex.from_arrays([df["local_date"] - timedelta(days=days), df["slot"]])
        df[name] = by_key.reindex(key).to_numpy()

    # Price level over the 7 days to midday on D-1: stands in for the cost of gas, which sets most prices.
    daily = df.groupby("local_date")["price"].mean()
    level = daily.rolling(7, min_periods=4).mean()
    df["level_7d"] = df["local_date"].map(lambda d: level.get(d - timedelta(days=2), np.nan))
    return df


def _train(train: pd.DataFrame) -> lgb.Booster:
    """Fit the model on rows with a known price and complete inputs."""
    ok = train.dropna(subset=["price", "leftover_mw", "level_7d"])
    return lgb.train(PARAMS, lgb.Dataset(ok[FEATURES], ok["price"]), num_boost_round=ROUNDS)


def backtest(feat: pd.DataFrame, start: date, end: date) -> pd.Series:
    """Rolling-origin forecasts: each month predicted by a model trained only on days before it."""
    out = []
    month = date(start.year, start.month, 1)
    while month <= end:
        nxt = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
        # The newest day usable in training is two days before the month starts (D-2 rule).
        train = feat[feat["local_date"] < month - timedelta(days=1)]
        test = feat[(feat["local_date"] >= max(month, start)) & (feat["local_date"] < nxt) & (feat["local_date"] <= end)]
        if len(test) and len(train) > 48 * 120:
            model = _train(train)
            out.append(pd.Series(model.predict(test[FEATURES]), index=test.index))
            log.info("Backtest %s: trained on %d half-hours", month, len(train))
        month = nxt
    return pd.concat(out) if out else pd.Series(dtype=float)


def forecast_day(feat: pd.DataFrame, day: date) -> pd.Series:
    """Forecast one day with a model trained on everything known by its decision time."""
    train = feat[feat["local_date"] <= day - timedelta(days=2)]
    test = feat[feat["local_date"] == day]
    if test.empty or test["leftover_mw"].isna().any():
        return pd.Series(dtype=float)
    return pd.Series(_train(train).predict(test[FEATURES]), index=test.index)


def accuracy(feat: pd.DataFrame) -> pd.DataFrame:
    """Daily forecast error against the actual price, for the model and the baseline."""
    df = feat.dropna(subset=["price", "forecast", "lag_7d"])

    def per_day(g: pd.DataFrame) -> pd.Series:
        corr = np.corrcoef(g["forecast"], g["price"])[0, 1] if g["price"].std() > 0 else np.nan
        return pd.Series({
            "ModelErrorGBP": np.mean(np.abs(g["forecast"] - g["price"])),
            "BaselineErrorGBP": np.mean(np.abs(g["lag_7d"] - g["price"])),
            "ShapeCorrelation": corr,
        })

    out = df.groupby("local_date").apply(per_day, include_groups=False).reset_index()
    return out.rename(columns={"local_date": "SettlementDate"}).round(3)
