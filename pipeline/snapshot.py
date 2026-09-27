"""Daily snapshot of the 48-hour national and regional forecasts.

Historical API calls only return the latest forecast for each period, so
the only way to measure genuine day-ahead accuracy is to keep what the
forecast said at the time. Run once a day:
    python -m pipeline.snapshot
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline import config
from pipeline.chunks import floor_half_hour
from pipeline.http import ApiError
from pipeline.ingest.carbon_intensity import CarbonIntensityClient
from pipeline.raw_paths import stamp
from pipeline.storage import EmptyResponseError, save_records

log = logging.getLogger("pipeline.snapshot")


def snapshot_path(scope: str, captured_at: datetime, raw_dir: Path = config.RAW_DIR) -> Path:
    """Where one snapshot file is stored."""
    folder = raw_dir / "forecast_snapshots" / captured_at.strftime("%Y-%m-%d")
    return folder / f"fw48h_{scope}_{stamp(captured_at)}.json"


def wrap(payload: dict[str, Any], captured_at: datetime, request_path: str) -> dict[str, Any]:
    """Add capture metadata alongside the untouched API response."""
    return {
        "captured_at": captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request_path": request_path,
        "data": payload.get("data"),
    }


def take_snapshots(
    client: CarbonIntensityClient, captured_at: datetime, raw_dir: Path = config.RAW_DIR
) -> dict[str, Path]:
    """Save national and regional fw48h forecasts; return the files written."""
    start = floor_half_hour(captured_at)
    written: dict[str, Path] = {}
    for scope in ("national", "regional"):
        payload = client.fetch_fw48h(scope, start)
        path = snapshot_path(scope, captured_at, raw_dir)
        rows = save_records(path, wrap(payload, captured_at, f"{scope}/fw48h/{start:%Y-%m-%dT%H:%MZ}"))
        log.info("%s snapshot: %d periods -> %s", scope, rows, path)
        written[scope] = path
    return written


def main() -> int:
    """Command-line entry point."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        take_snapshots(CarbonIntensityClient(), datetime.now(timezone.utc))
    except (ApiError, EmptyResponseError) as exc:
        log.error("snapshot failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
