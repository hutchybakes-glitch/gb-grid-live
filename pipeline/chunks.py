"""Split a UTC date range into windows the APIs will accept."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

from pipeline.config import MAX_CHUNK_DAYS


@dataclass(frozen=True)
class Chunk:
    """A half-open UTC window [start, end)."""

    start: datetime
    end: datetime


def iter_chunks(start: datetime, end: datetime, days: int = MAX_CHUNK_DAYS) -> Iterator[Chunk]:
    """Yield consecutive windows of at most ``days`` days covering [start, end).

    Windows are anchored to ``start`` so the same range always produces the
    same chunk boundaries, which is what makes the backfill resumable.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware (UTC)")
    if days < 1 or days > MAX_CHUNK_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_CHUNK_DAYS}")
    step = timedelta(days=days)
    cursor = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    while cursor < end:
        chunk_end = min(cursor + step, end)
        yield Chunk(cursor, chunk_end)
        cursor = chunk_end


def floor_half_hour(moment: datetime) -> datetime:
    """Round a datetime down to the start of its half-hour, in UTC."""
    moment = moment.astimezone(timezone.utc)
    return moment.replace(minute=30 if moment.minute >= 30 else 0, second=0, microsecond=0)
