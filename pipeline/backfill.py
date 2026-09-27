"""Resumable, idempotent backfill of raw data for both sources.

Usage (PowerShell):
    python -m pipeline.backfill                      # 2023-01-01 to today, all sources
    python -m pipeline.backfill --start 2024-01-01 --sources ci_national
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pipeline import config
from pipeline.chunks import Chunk, iter_chunks
from pipeline.http import ApiError
from pipeline.ingest import pvlive
from pipeline.ingest.carbon_intensity import RANGE_ENDPOINTS, CarbonIntensityClient, max_days
from pipeline.ingest.pvlive import PVLiveClient
from pipeline.raw_paths import chunk_path, stale_siblings
from pipeline.storage import EmptyResponseError, save_records, write_json_atomic

log = logging.getLogger("pipeline.backfill")

Fetcher = Callable[[Chunk], dict[str, Any]]


@dataclass
class BackfillStats:
    """Counts reported at the end of a run."""

    fetched: int = 0
    skipped: int = 0
    empty: int = 0
    failed: list[str] = field(default_factory=list)


def parse_date(text: str) -> datetime:
    """Parse ``YYYY-MM-DD`` as midnight UTC."""
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def today_midnight_utc() -> datetime:
    """Midnight UTC today: the backfill stops here so every chunk covers whole days."""
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def build_fetchers(ci: CarbonIntensityClient, pv: PVLiveClient, raw_dir: Path) -> dict[str, Fetcher]:
    """Map each raw source name to a function that fetches one chunk of it."""
    fetchers: dict[str, Fetcher] = {
        name: (lambda c, n=name: ci.fetch_range(n, c.start, c.end)) for name in RANGE_ENDPOINTS
    }
    fetchers["pvlive_gsp0"] = lambda c: pv.fetch_range("gsp", pvlive.NATIONAL_GSP_ID, c.start, c.end)
    # PES ids are looked up from the API (they run 10-23, not 1-14) and the
    # list itself is kept as raw data so Phase 2 can map areas to regions.
    pes_list = pv.fetch_pes_list()
    write_json_atomic(raw_dir / "pvlive_reference" / "pes_list.json", pes_list)
    for pes_id in pvlive.pes_ids(pes_list):
        fetchers[f"pvlive_pes{pes_id}"] = lambda c, i=pes_id: pv.fetch_range("pes", i, c.start, c.end)
    return fetchers


def backfill_source(
    source: str, fetch: Fetcher, chunks: list[Chunk], raw_dir: Path, stats: BackfillStats
) -> None:
    """Fetch every missing chunk of one source, skipping those already on disk."""
    for chunk in chunks:
        path = chunk_path(source, chunk, raw_dir)
        if path.exists():
            stats.skipped += 1
            continue
        try:
            rows = save_records(path, fetch(chunk))
        except EmptyResponseError:
            stats.empty += 1
            log.warning("%s %s: empty response, nothing written", source, path.name)
            continue
        except ApiError as exc:
            stats.failed.append(f"{source} {path.name}: {exc}")
            log.error("%s %s: %s", source, path.name, exc)
            continue
        for old in stale_siblings(path):
            old.unlink()
        stats.fetched += 1
        log.info("%s %s: %d rows", source, path.name, rows)


def run(start: datetime, end: datetime, sources: list[str] | None, raw_dir: Path = config.RAW_DIR) -> BackfillStats:
    """Backfill ``sources`` (all if None) for [start, end) and return run statistics."""
    ci, pv = CarbonIntensityClient(), PVLiveClient()
    fetchers = build_fetchers(ci, pv, raw_dir)
    unknown = set(sources or []) - set(fetchers)
    if unknown:
        raise SystemExit(f"unknown sources: {sorted(unknown)}; choose from {sorted(fetchers)}")
    stats = BackfillStats()
    for source, fetch in fetchers.items():
        if sources and source not in sources:
            continue
        chunks = list(iter_chunks(start, end, days=max_days(source)))
        log.info("== %s: %d chunks ==", source, len(chunks))
        backfill_source(source, fetch, chunks, raw_dir, stats)
    return stats


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point; returns a non-zero exit code if any chunk failed."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=parse_date, default=config.BACKFILL_START)
    parser.add_argument("--end", type=parse_date, default=None, help="exclusive; default today 00:00 UTC")
    parser.add_argument("--sources", nargs="*", default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stats = run(args.start, args.end or today_midnight_utc(), args.sources)
    log.info(
        "done: fetched %d, skipped %d existing, empty %d, failed %d",
        stats.fetched, stats.skipped, stats.empty, len(stats.failed),
    )
    for line in stats.failed:
        log.error("FAILED %s", line)
    return 1 if stats.failed else 0


if __name__ == "__main__":
    sys.exit(main())
