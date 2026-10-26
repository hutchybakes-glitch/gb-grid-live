"""State for the battery pipeline: one CSV per source under ``data/battery/state``.

The published ``powerbi-data`` branch carries these files, so each run fetches only what is new.
Every input is re-fetchable, so losing the state costs one slow backfill, never data.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from pipeline.battery import settings

log = logging.getLogger(__name__)

# Source name -> value columns kept in its state file.
SOURCES: dict[str, list[str]] = {
    "prices": ["price"],
    "wind_solar": ["wind_mw", "solar_mw"],
    "demand": ["demand_mw"],
    "carbon": ["carbon"],
    "forecasts": ["forecast", "made_utc", "model"],
}


def path(name: str) -> Path:
    """Where a source's state file lives."""
    return settings.STATE_DIR / f"{name}.csv"


def load(name: str) -> pd.DataFrame:
    """Read a state file, or an empty frame with the right columns if there isn't one yet."""
    p = path(name)
    cols = ["period_start_utc", *SOURCES[name]]
    if not p.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(p)
    df["period_start_utc"] = pd.to_datetime(df["period_start_utc"], utc=True)
    return df[cols]


def save(name: str, df: pd.DataFrame) -> None:
    """Write a state file, sorted, one row per half-hour."""
    settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = df.drop_duplicates("period_start_utc", keep="last").sort_values("period_start_utc")
    out.to_csv(path(name), index=False, date_format="%Y-%m-%dT%H:%M:%SZ")


def merge(name: str, old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """New rows replace old rows for the same half-hour; an empty fetch never removes good data."""
    if new.empty:
        return old
    frames = [f for f in (old, new[old.columns.intersection(new.columns)]) if not f.empty]
    return pd.concat(frames).drop_duplicates("period_start_utc", keep="last")


def local_days(df: pd.DataFrame) -> set[date]:
    """The UK local days that have at least one row."""
    if df.empty:
        return set()
    return set(df["period_start_utc"].dt.tz_convert(settings.UK).dt.date)


def days_to_fetch(df: pd.DataFrame, first: date, last: date) -> list[date]:
    """Days with no rows yet, plus the most recent days (late corrections still arrive)."""
    have = local_days(df)
    recent_from = last - timedelta(days=settings.REFETCH_RECENT_DAYS - 1)
    days = []
    d = first
    while d <= last:
        if d not in have or d >= recent_from:
            days.append(d)
        d += timedelta(days=1)
    return days


def runs(days: list[date]) -> list[tuple[date, date]]:
    """Group a sorted list of days into consecutive (first, last) runs, so fetches can be chunked."""
    out: list[tuple[date, date]] = []
    for d in days:
        if out and d == out[-1][1] + timedelta(days=1):
            out[-1] = (out[-1][0], d)
        else:
            out.append((d, d))
    return out
