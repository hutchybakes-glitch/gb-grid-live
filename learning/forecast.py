# The module description (a docstring can't hold comments, so this one covers all its lines).
"""Tomorrow's wholesale price forecast, from tomorrow's wind, solar and demand forecasts.

There is no free source of tomorrow's GB wholesale price, so the planner needs a forecast. Every input is
something that was published before 17:15 UTC the day before (see ``sources.decision_cutoff``), and the
backtest retrains month by month on earlier data only, so its error is the error a real user would have had.
The yardstick is a naive baseline: the same half-hour one week earlier.
"""
# Allows modern type-hint syntax everywhere in this file.
from __future__ import annotations

# The standard way to print progress messages.
import logging
# date = a calendar day; timedelta = a length of time, for "two days earlier" sums.
from datetime import date, timedelta

# LightGBM: a fast machine-learning library that builds many small decision trees and adds them up.
import lightgbm as lgb
# numpy does fast maths on arrays of numbers.
import numpy as np
# pandas holds tables of data (DataFrames) and does grouping and joining.
import pandas as pd

# Our battery settings (including the UK time zone).
from pipeline.battery import settings

# Create a logger named after this module, so log lines show where they came from.
log = logging.getLogger(__name__)

# A label saved with each forecast, so we know which model made it if the model changes later.
MODEL_VERSION = "lgbm-v1"
# The inputs the model learns from.
FEATURES = [
    # Demand left after wind and sun, total demand, wind, solar, half-hour of the day, day of week, month...
    "leftover_mw", "demand_mw", "wind_mw", "solar_mw", "slot", "dow", "month",
    # ...the recent price level, and the price at the same half-hour 2 days and 7 days earlier.
    "level_7d", "lag_2d", "lag_7d",
]
# The model's settings.
PARAMS = {
    # Predict a number (the price); learn slowly; trees of up to 31 leaves; at least 40 half-hours per leaf.
    "objective": "regression", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 40,
    # Each tree sees 90% of the inputs and 80% of the rows (reduces overfitting); stay quiet; fixed seed so runs repeat.
    "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1, "seed": 7,
}
# How many trees to build.
ROUNDS = 400


# Adds the model's input columns to the table of half-hours.
def build_features(hh: pd.DataFrame) -> pd.DataFrame:
    # The docstring.
    """Add model inputs to the half-hour frame. Uses only what was known at the decision time.

    Expects columns period_start_utc, price, wind_mw, solar_mw, demand_mw.
    """
    # Work on a copy so the caller's table isn't changed.
    df = hh.copy()
    # Each half-hour's start time in UK local time (GMT or BST).
    local = df["period_start_utc"].dt.tz_convert(settings.UK)
    # The UK calendar day each half-hour belongs to.
    df["local_date"] = local.dt.date
    # Slot = local half-hour of the day (0-47); on clock-change days the repeated or skipped hour shares slots.
    # Hour x 2, plus 1 if it starts at half past.
    df["slot"] = local.dt.hour * 2 + local.dt.minute // 30
    # Day of the week (0 = Monday): weekends have lower demand.
    df["dow"] = local.dt.dayofweek
    # Month of the year (1-12): captures the seasons.
    df["month"] = local.dt.month
    # The key input: demand that wind and sun can't cover, which gas and other plants must fill.
    df["leftover_mw"] = df["demand_mw"] - df["wind_mw"] - df["solar_mw"]

    # Lags by local day and slot: D-2 is the latest whole day known at 17:15 on D-1.
    # A lookup of the price for every (day, half-hour) pair.
    by_key = df.groupby(["local_date", "slot"])["price"].mean()
    # lag_14d is not a model feature: it stands in for last week's prices when that week has gaps (LastWeek strategy).
    # For 2, 7 and 14 days back...
    for days, name in ((2, "lag_2d"), (7, "lag_7d"), (14, "lag_14d")):
        # ...build the (earlier day, same half-hour) pair for every row...
        key = pd.MultiIndex.from_arrays([df["local_date"] - timedelta(days=days), df["slot"]])
        # ...and look up that earlier price (blank if it's missing).
        df[name] = by_key.reindex(key).to_numpy()

    # Price level over the 7 days to midday on D-1: stands in for the cost of gas, which sets most prices.
    # The average price for each day.
    daily = df.groupby("local_date")["price"].mean()
    # The 7-day rolling average of those daily prices (needs at least 4 days).
    level = daily.rolling(7, min_periods=4).mean()
    # For each row, the rolling average ending two days earlier (the newest one known in time).
    df["level_7d"] = df["local_date"].map(lambda d: level.get(d - timedelta(days=2), np.nan))
    # Return the table with the new columns.
    return df


# Trains one model.
def _train(train: pd.DataFrame) -> lgb.Booster:
    # The docstring.
    """Fit the model on rows with a known price and complete inputs."""
    # Keep only rows where the price and the key inputs are present.
    ok = train.dropna(subset=["price", "leftover_mw", "level_7d"])
    # Build the trees, learning to predict price from the inputs.
    return lgb.train(PARAMS, lgb.Dataset(ok[FEATURES], ok["price"]), num_boost_round=ROUNDS)


# Tests the forecast on the past honestly: each month forecast by a model that never saw it.
def backtest(feat: pd.DataFrame, start: date, end: date) -> pd.Series:
    # The docstring.
    """Rolling-origin forecasts: each month predicted by a model trained only on days before it."""
    # The forecasts collected so far, one batch per month.
    out = []
    # Start at the first day of the starting month.
    month = date(start.year, start.month, 1)
    # Work through the months until the end date.
    while month <= end:
        # The first day of the next month (December rolls over into January of the next year).
        nxt = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
        # The newest day usable in training is two days before the month starts (D-2 rule).
        # Training data: every day before the day before this month starts.
        train = feat[feat["local_date"] < month - timedelta(days=1)]
        # Test data: the days of this month that fall inside the requested range.
        test = feat[(feat["local_date"] >= max(month, start)) & (feat["local_date"] < nxt) & (feat["local_date"] <= end)]
        # Only forecast if there's something to test and at least 120 days to learn from.
        if len(test) and len(train) > 48 * 120:
            # Train a fresh model on the past only.
            model = _train(train)
            # Forecast this month and keep the results, labelled by row.
            out.append(pd.Series(model.predict(test[FEATURES]), index=test.index))
            # Log progress.
            log.info("Backtest %s: trained on %d half-hours", month, len(train))
        # Move on to the next month.
        month = nxt
    # Join all the months together (or return an empty series if nothing was forecast).
    return pd.concat(out) if out else pd.Series(dtype=float)


# Forecasts a single day, e.g. tomorrow.
def forecast_day(feat: pd.DataFrame, day: date) -> pd.Series:
    # The docstring.
    """Forecast one day with a model trained on everything known by its decision time."""
    # Train on every day up to two days before the target day.
    train = feat[feat["local_date"] <= day - timedelta(days=2)]
    # The rows for the day being forecast.
    test = feat[feat["local_date"] == day]
    # If the day has no rows, or any half-hour lacks its wind, solar and demand forecast...
    if test.empty or test["leftover_mw"].isna().any():
        # ...return nothing rather than a forecast with holes in it.
        return pd.Series(dtype=float)
    # Train and forecast in one go.
    return pd.Series(_train(train).predict(test[FEATURES]), index=test.index)


# Scores the forecast day by day.
def accuracy(feat: pd.DataFrame) -> pd.DataFrame:
    # The docstring.
    """Daily forecast error against the actual price, for the model and the baseline."""
    # Keep rows that have an actual price, a forecast and a last-week price to compare.
    df = feat.dropna(subset=["price", "forecast", "lag_7d"])

    # Works out the scores for one day's rows.
    def per_day(g: pd.DataFrame) -> pd.Series:
        # How well the forecast's shape follows the actual prices (1 = perfectly); blank if prices were flat.
        corr = np.corrcoef(g["forecast"], g["price"])[0, 1] if g["price"].std() > 0 else np.nan
        # Return the day's three scores.
        return pd.Series({
            # The model's average miss, in £/MWh.
            "ModelErrorGBP": np.mean(np.abs(g["forecast"] - g["price"])),
            # The "same time last week" guess's average miss.
            "BaselineErrorGBP": np.mean(np.abs(g["lag_7d"] - g["price"])),
            # The shape score.
            "ShapeCorrelation": corr,
        })

    # Score every day (the day column isn't passed into per_day), then turn the day back into a column.
    out = df.groupby("local_date").apply(per_day, include_groups=False).reset_index()
    # Rename the day column to match the report's name and round to 3 decimals.
    return out.rename(columns={"local_date": "SettlementDate"}).round(3)
