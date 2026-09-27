# This line is the module's description: a short note on what the file is for.
"""Split a UTC date range into windows the APIs will accept."""
# This lets us write type hints like "list[str]" and "X | None" freely, even for classes defined later.
from __future__ import annotations

# "dataclass" is a shortcut for making a small class that just holds values.
from dataclasses import dataclass
# datetime = a point in time; timedelta = a length of time; timezone lets us say "this is UTC".
from datetime import datetime, timedelta, timezone
# Iterator is a type hint meaning "something you can loop over, one item at a time".
from typing import Iterator

# Pull in the 14-day limit from the shared settings file, so the number lives in one place only.
from pipeline.config import MAX_CHUNK_DAYS


# frozen=True means a Chunk cannot be changed after it is created, which makes it safe to compare and reuse.
@dataclass(frozen=True)
# Define a tiny class called Chunk to represent one slice of time.
class Chunk:
    # The docstring: the window includes its start but not its end ("half-open").
    """A half-open UTC window [start, end)."""

    # The first moment inside this chunk.
    start: datetime
    # The moment just after this chunk ends (where the next chunk starts).
    end: datetime


# A function that takes a start, an end and a chunk size, and hands back chunks one by one.
def iter_chunks(start: datetime, end: datetime, days: int = MAX_CHUNK_DAYS) -> Iterator[Chunk]:
    # The docstring explains what the function does.
    """Yield consecutive windows of at most ``days`` days covering [start, end).

    # This is the key design idea, explained inside the docstring.
    Windows are anchored to ``start`` so the same range always produces the
    same chunk boundaries, which is what makes the backfill resumable.
    """
    # A datetime with no time zone is ambiguous (UK time? UTC?), so refuse it outright.
    if start.tzinfo is None or end.tzinfo is None:
        # Stop with a clear error message.
        raise ValueError("start and end must be timezone-aware (UTC)")
    # Guard against a chunk size that is zero, negative, or bigger than the API allows.
    if days < 1 or days > MAX_CHUNK_DAYS:
        # Stop with a clear error message.
        raise ValueError(f"days must be between 1 and {MAX_CHUNK_DAYS}")
    # Turn the number of days into a length of time we can add to a datetime.
    step = timedelta(days=days)
    # "cursor" marks where the next chunk begins; convert to UTC to be sure.
    cursor = start.astimezone(timezone.utc)
    # Make sure the end is in UTC too, so comparisons are like-for-like.
    end = end.astimezone(timezone.utc)
    # Keep going until the cursor reaches the end of the range.
    while cursor < end:
        # This chunk ends one step later, unless that would overshoot the overall end.
        chunk_end = min(cursor + step, end)
        # Hand this chunk to whoever is looping over us, then pause here until they ask for the next one.
        yield Chunk(cursor, chunk_end)
        # Move the cursor forward so the next chunk starts exactly where this one ended (no gaps, no overlaps).
        cursor = chunk_end


# A helper that rounds a time down to the nearest half-hour (e.g. 18:47 becomes 18:30).
def floor_half_hour(moment: datetime) -> datetime:
    # The docstring.
    """Round a datetime down to the start of its half-hour, in UTC."""
    # Convert to UTC first so we never round a UK local time by mistake.
    moment = moment.astimezone(timezone.utc)
    # Keep the hour, set minutes to 30 or 0, and clear seconds and microseconds.
    return moment.replace(minute=30 if moment.minute >= 30 else 0, second=0, microsecond=0)
