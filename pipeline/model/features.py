"""Feature building with an explicit information cut-off (no leakage).

For a target period t and a horizon of h half-hours, the model may use:
- the official forecast for t itself (that is what it corrects), and
- anything measured at or before t - h: past errors, past solar output.
Calendar features for t are always known in advance.

All shifts are done on a complete half-hour time index, so a missing period
shifts in as NaN instead of silently pulling in the wrong row.
"""
from __future__ import annotations

import pandas as pd

HALF_HOUR = pd.Timedelta(minutes=30)
FEATURES: list[str] = [
    "forecast",
    "err_lag",
    "err_lag_mean_6h",
    "err_lag_mean_24h",
    "err_same_slot_prev_day",
    "forecast_change",
    "solar_lag_mw",
    "solar_same_slot_prev_day_mw",
    "local_hour",
    "day_of_week",
    "month",
]


def complete_index(df: pd.DataFrame) -> pd.DataFrame:
    """Reindex on every half-hour between the first and last period."""
    idx = pd.date_range(df.index.min(), df.index.max(), freq=HALF_HOUR, name=df.index.name)
    return df.reindex(idx)


def build_features(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Return features plus ``target`` (actual - forecast) for every period.

    ``df`` is indexed by UTC period start and has columns ``forecast``,
    ``actual`` and ``solar_mw``. ``horizon`` is in half-hours (2 = 1 hour ahead).
    """
    if horizon < 1:
        raise ValueError("horizon must be at least one half-hour")
    d = complete_index(df.sort_index())
    err = d["actual"] - d["forecast"]
    out = pd.DataFrame(index=d.index)
    out["forecast"] = d["forecast"]
    # Everything below is shifted by at least `horizon`: known at issue time.
    out["err_lag"] = err.shift(horizon)
    out["err_lag_mean_6h"] = err.shift(horizon).rolling(12, min_periods=6).mean()
    out["err_lag_mean_24h"] = err.shift(horizon).rolling(48, min_periods=24).mean()
    out["err_same_slot_prev_day"] = err.shift(max(48, horizon))
    out["forecast_change"] = d["forecast"] - d["forecast"].shift(horizon)
    out["solar_lag_mw"] = d["solar_mw"].shift(horizon)
    out["solar_same_slot_prev_day_mw"] = d["solar_mw"].shift(max(48, horizon))
    local = d.index.tz_localize("UTC").tz_convert("Europe/London")
    out["local_hour"] = local.hour + local.minute / 60
    out["day_of_week"] = local.dayofweek
    out["month"] = local.month
    out["actual"] = d["actual"]
    out["target"] = err
    return out
