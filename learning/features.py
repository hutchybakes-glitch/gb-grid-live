# The module description: why this file is careful about time.
"""Feature building with an explicit information cut-off (no leakage).

For a target period t and a horizon of h half-hours, the model may use:
- the official forecast for t itself (that is what it corrects), and
- anything measured at or before t - h: past errors, past solar output.
Calendar features for t are always known in advance.

All shifts are done on a complete half-hour time index, so a missing period
shifts in as NaN instead of silently pulling in the wrong row.
"""
# Allows modern type-hint syntax.
from __future__ import annotations

# pandas: the table library used for time series.
import pandas as pd

# The length of one period, used to build a complete time index.
HALF_HOUR = pd.Timedelta(minutes=30)
# The exact list of columns the model is allowed to see. Anything not listed here is never used.
FEATURES: list[str] = [
    # The official forecast for the target half-hour.
    "forecast",
    # The most recent forecast error known at issue time.
    "err_lag",
    # Average of known errors over the 6 hours before issue time.
    "err_lag_mean_6h",
    # Average of known errors over the 24 hours before issue time.
    "err_lag_mean_24h",
    # The error at the same time of day, one day earlier.
    "err_same_slot_prev_day",
    # How much the forecast for t differs from the forecast at issue time.
    "forecast_change",
    # The most recent solar output known at issue time.
    "solar_lag_mw",
    # Solar output at the same time of day, one day earlier.
    "solar_same_slot_prev_day_mw",
    # UK local time of day (e.g. 13.5 means 13:30).
    "local_hour",
    # Day of week (0 = Monday).
    "day_of_week",
    # Month number (1 = January).
    "month",
]


# Make sure there is exactly one row for every half-hour, even missing ones.
def complete_index(df: pd.DataFrame) -> pd.DataFrame:
    # The docstring.
    """Reindex on every half-hour between the first and last period."""
    # Build a list of every half-hour from the first to the last timestamp.
    idx = pd.date_range(df.index.min(), df.index.max(), freq=HALF_HOUR, name=df.index.name)
    # Line the data up against that list; missing half-hours become empty (NaN) rows.
    return df.reindex(idx)


# Build the model's input table for one forecast horizon.
def build_features(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    # The docstring.
    """Return features plus ``target`` (actual - forecast) for every period.

    ``df`` is indexed by UTC period start and has columns ``forecast``,
    ``actual`` and ``solar_mw``. ``horizon`` is in half-hours (2 = 1 hour ahead).
    """
    # A horizon of zero would let the model peek at the answer.
    if horizon < 1:
        # Refuse clearly.
        raise ValueError("horizon must be at least one half-hour")
    # Sort by time and fill in any missing half-hours, so "shift by N" really means "N half-hours earlier".
    d = complete_index(df.sort_index())
    # The forecast error for every half-hour (what the model learns to predict).
    err = d["actual"] - d["forecast"]
    # Start an empty output table with the same time index.
    out = pd.DataFrame(index=d.index)
    # The forecast for t itself is allowed: it is what we are correcting.
    out["forecast"] = d["forecast"]
    # The comment below is the key rule of the whole file.
    # Everything below is shifted by at least `horizon`: known at issue time.
    # shift(horizon) moves each value `horizon` half-hours later, so row t sees the error from t - horizon.
    out["err_lag"] = err.shift(horizon)
    # Average of the 12 known errors before the cut-off (6 hours), needing at least 6 of them.
    out["err_lag_mean_6h"] = err.shift(horizon).rolling(12, min_periods=6).mean()
    # Average of the 48 known errors before the cut-off (24 hours), needing at least 24.
    out["err_lag_mean_24h"] = err.shift(horizon).rolling(48, min_periods=24).mean()
    # Same time yesterday, or further back if the horizon is longer than a day.
    out["err_same_slot_prev_day"] = err.shift(max(48, horizon))
    # Forecast for t minus the forecast that applied at issue time.
    out["forecast_change"] = d["forecast"] - d["forecast"].shift(horizon)
    # Latest known solar output at issue time.
    out["solar_lag_mw"] = d["solar_mw"].shift(horizon)
    # Solar output at the same time yesterday (or earlier).
    out["solar_same_slot_prev_day_mw"] = d["solar_mw"].shift(max(48, horizon))
    # Convert the UTC timestamps to UK local time, just for the calendar features.
    local = d.index.tz_localize("UTC").tz_convert("Europe/London")
    # Time of day as a decimal hour, in UK time (so 13:30 BST is 13.5).
    out["local_hour"] = local.hour + local.minute / 60
    # Day of the week in UK time.
    out["day_of_week"] = local.dayofweek
    # Month in UK time.
    out["month"] = local.month
    # Keep the actual value so the backtest can score predictions (not a feature).
    out["actual"] = d["actual"]
    # The target: the error the model tries to predict (not a feature).
    out["target"] = err
    # Hand back the finished table.
    return out
