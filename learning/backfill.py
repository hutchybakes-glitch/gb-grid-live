# The module description, including how to run it.
"""Resumable, idempotent backfill of raw data for both sources.

Usage (PowerShell):
    python -m pipeline.backfill                      # 2023-01-01 to today, all sources
    python -m pipeline.backfill --start 2024-01-01 --sources ci_national
"""
# Allows modern type-hint syntax.
from __future__ import annotations

# Reads options typed on the command line (like --start).
import argparse
# Prints timestamped progress messages.
import logging
# Lets us set the program's exit code (0 = success, 1 = something failed).
import sys
# dataclass makes a simple value-holding class; field sets up a default empty list safely.
from dataclasses import dataclass, field
# Dates, times and UTC.
from datetime import datetime, timezone
# Path represents a file or folder location in a way that works on Windows and Linux.
from pathlib import Path
# Type-hint helpers.
from typing import Any, Callable

# Shared settings.
from pipeline import config
# Our date-range chopper.
from pipeline.chunks import Chunk, iter_chunks
# The error raised when an API gives up after retries.
from pipeline.http import ApiError
# The PV_Live module (for helper functions like pes_ids).
from pipeline.ingest import pvlive
# The Carbon Intensity client, its list of endpoints, and each endpoint's maximum chunk length.
from pipeline.ingest.carbon_intensity import RANGE_ENDPOINTS, CarbonIntensityClient, max_days
# The PV_Live client.
from pipeline.ingest.pvlive import PVLiveClient
# Rules for naming raw files, and finding older partial versions of the same chunk.
from pipeline.raw_paths import chunk_path, stale_siblings
# Safe file-writing helpers.
from pipeline.storage import EmptyResponseError, save_records, write_json_atomic

# A logger for this module.
log = logging.getLogger("pipeline.backfill")

# A name for "a function that takes a Chunk and returns the JSON for it".
Fetcher = Callable[[Chunk], dict[str, Any]]


# Make BackfillStats a simple value-holding class.
@dataclass
# A small scoreboard for one run.
class BackfillStats:
    # The docstring.
    """Counts reported at the end of a run."""

    # How many chunks were downloaded this run.
    fetched: int = 0
    # How many were already on disk and skipped (this is what makes resuming cheap).
    skipped: int = 0
    # How many came back with no data (nothing written).
    empty: int = 0
    # Descriptions of chunks that failed, so they can be listed at the end.
    failed: list[str] = field(default_factory=list)


# Turn text like "2023-01-01" into a UTC datetime.
def parse_date(text: str) -> datetime:
    # The docstring.
    """Parse ``YYYY-MM-DD`` as midnight UTC."""
    # Parse the text, then label it as UTC.
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


# Work out today's midnight in UTC.
def today_midnight_utc() -> datetime:
    # The docstring.
    """Midnight UTC today: the backfill stops here so every chunk covers whole days."""
    # Take "now" and zero out the time part.
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


# Build a lookup table: source name -> function that downloads one chunk of that source.
def build_fetchers(ci: CarbonIntensityClient, pv: PVLiveClient, raw_dir: Path) -> dict[str, Fetcher]:
    # The docstring.
    """Map each raw source name to a function that fetches one chunk of it."""
    # One entry per Carbon Intensity endpoint; "n=name" freezes the name for each little function.
    fetchers: dict[str, Fetcher] = {
        # For each endpoint name, a function that fetches that endpoint for a given chunk.
        name: (lambda c, n=name: ci.fetch_range(n, c.start, c.end)) for name in RANGE_ENDPOINTS
    }
    # The national solar estimate (PV_Live GSP 0).
    fetchers["pvlive_gsp0"] = lambda c: pv.fetch_range("gsp", pvlive.NATIONAL_GSP_ID, c.start, c.end)
    # Explains why the next lines look up ids instead of hard-coding them.
    # PES ids are looked up from the API (they run 10-23, not 1-14) and the
    # This continues the explanation.
    # list itself is kept as raw data so Phase 2 can map areas to regions.
    # Ask PV_Live for its list of regional (PES) areas.
    pes_list = pv.fetch_pes_list()
    # Save that list to disk as reference data.
    write_json_atomic(raw_dir / "pvlive_reference" / "pes_list.json", pes_list)
    # For every regional area id...
    for pes_id in pvlive.pes_ids(pes_list):
        # ...add a fetcher named e.g. "pvlive_pes16"; "i=pes_id" freezes the id for each function.
        fetchers[f"pvlive_pes{pes_id}"] = lambda c, i=pes_id: pv.fetch_range("pes", i, c.start, c.end)
    # Hand back the finished table.
    return fetchers


# Download every missing chunk for one source.
def backfill_source(
    # The source name, a download function, the list of chunks, where to save, and the scoreboard.
    source: str, fetch: Fetcher, chunks: list[Chunk], raw_dir: Path, stats: BackfillStats
# Returns nothing (results go into stats).
) -> None:
    # The docstring.
    """Fetch every missing chunk of one source, skipping those already on disk."""
    # Go through the chunks in date order.
    for chunk in chunks:
        # Work out where this chunk's file should be.
        path = chunk_path(source, chunk, raw_dir)
        # If it's already there, a previous run finished it: this is the "resume" trick.
        if path.exists():
            # Count it as skipped.
            stats.skipped += 1
            # Move on to the next chunk without calling the API.
            continue
        # Try to download and save; several things could go wrong, handled below.
        try:
            # Download, then save only if it has data; returns the row count.
            rows = save_records(path, fetch(chunk))
        # The API replied but with no rows.
        except EmptyResponseError:
            # Count it.
            stats.empty += 1
            # Warn, but don't stop the whole backfill.
            log.warning("%s %s: empty response, nothing written", source, path.name)
            # Next chunk.
            continue
        # The API kept failing even after retries.
        except ApiError as exc:
            # Remember it for the end-of-run report.
            stats.failed.append(f"{source} {path.name}: {exc}")
            # Log the error now too.
            log.error("%s %s: %s", source, path.name, exc)
            # Carry on with other chunks; rerunning later will retry just this one.
            continue
        # If an older, shorter version of this chunk exists (from a previous day's run)...
        for old in stale_siblings(path):
            # ...delete it, because the new file covers everything it did and more.
            old.unlink()
        # Count the successful download.
        stats.fetched += 1
        # Log progress.
        log.info("%s %s: %d rows", source, path.name, rows)


# Run the backfill for a date range and a set of sources.
def run(start: datetime, end: datetime, sources: list[str] | None, raw_dir: Path = config.RAW_DIR) -> BackfillStats:
    # The docstring.
    """Backfill ``sources`` (all if None) for [start, end) and return run statistics."""
    # Create one client per API.
    ci, pv = CarbonIntensityClient(), PVLiveClient()
    # Build the source -> download-function table.
    fetchers = build_fetchers(ci, pv, raw_dir)
    # Check the user didn't ask for a source name that doesn't exist.
    unknown = set(sources or []) - set(fetchers)
    # If they did...
    if unknown:
        # ...stop and list the valid names.
        raise SystemExit(f"unknown sources: {sorted(unknown)}; choose from {sorted(fetchers)}")
    # Start a fresh scoreboard.
    stats = BackfillStats()
    # Go through each source in turn.
    for source, fetch in fetchers.items():
        # If specific sources were requested, skip the others.
        if sources and source not in sources:
            # Next source.
            continue
        # Chop the date range into chunks: 14 days, or 13 for regional (its API rejects exactly 14).
        chunks = list(iter_chunks(start, end, days=max_days(source)))
        # Log a header line for this source.
        log.info("== %s: %d chunks ==", source, len(chunks))
        # Download its missing chunks.
        backfill_source(source, fetch, chunks, raw_dir, stats)
    # Return the scoreboard.
    return stats


# The function run from the command line.
def main(argv: list[str] | None = None) -> int:
    # The docstring.
    """Command-line entry point; returns a non-zero exit code if any chunk failed."""
    # Set up the command-line option reader, using the module description as help text.
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # --start: first day to fetch (default 2023-01-01).
    parser.add_argument("--start", type=parse_date, default=config.BACKFILL_START)
    # --end: stop before this day (default: today at midnight UTC).
    parser.add_argument("--end", type=parse_date, default=None, help="exclusive; default today 00:00 UTC")
    # --sources: optional list of source names to fetch.
    parser.add_argument("--sources", nargs="*", default=None)
    # Read the options the user typed.
    args = parser.parse_args(argv)
    # Turn on INFO-level logging with timestamps.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Do the work.
    stats = run(args.start, args.end or today_midnight_utc(), args.sources)
    # Print a one-line summary.
    log.info(
        # The template.
        "done: fetched %d, skipped %d existing, empty %d, failed %d",
        # The values.
        stats.fetched, stats.skipped, stats.empty, len(stats.failed),
    )
    # List every failure so nothing is hidden.
    for line in stats.failed:
        # One error line per failed chunk.
        log.error("FAILED %s", line)
    # Exit code 1 if anything failed (so a scheduler notices), otherwise 0.
    return 1 if stats.failed else 0


# Only run main() when the file is run directly, not when it is imported.
if __name__ == "__main__":
    # Run main and pass its result to the operating system as the exit code.
    sys.exit(main())
