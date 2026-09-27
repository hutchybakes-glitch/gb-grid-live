# The module description, explaining why snapshots exist at all.
"""Daily snapshot of the 48-hour national and regional forecasts.

Historical API calls only return the latest forecast for each period, so
the only way to measure genuine day-ahead accuracy is to keep what the
forecast said at the time. Run once a day:
    python -m pipeline.snapshot
"""
# Allows modern type-hint syntax.
from __future__ import annotations

# Timestamped log messages.
import logging
# Lets us return an exit code to the operating system.
import sys
# Dates, times and UTC.
from datetime import datetime, timezone
# File locations.
from pathlib import Path
# "Any" = any type.
from typing import Any

# Shared settings.
from pipeline import config
# Helper that rounds a time down to the half-hour.
from pipeline.chunks import floor_half_hour
# The error raised when an API gives up after retries.
from pipeline.http import ApiError
# The Carbon Intensity client.
from pipeline.ingest.carbon_intensity import CarbonIntensityClient
# Makes a compact, Windows-safe timestamp for file names.
from pipeline.raw_paths import stamp
# Safe saving, plus the "empty response" error.
from pipeline.storage import EmptyResponseError, save_records

# A logger for this module.
log = logging.getLogger("pipeline.snapshot")


# Decide where a snapshot file goes.
def snapshot_path(scope: str, captured_at: datetime, raw_dir: Path = config.RAW_DIR) -> Path:
    # The docstring.
    """Where one snapshot file is stored."""
    # One folder per day, e.g. data/raw/forecast_snapshots/2026-09-27.
    folder = raw_dir / "forecast_snapshots" / captured_at.strftime("%Y-%m-%d")
    # File name includes the scope and capture time, so snapshots never overwrite each other.
    return folder / f"fw48h_{scope}_{stamp(captured_at)}.json"


# Package the API response together with when and how we captured it.
def wrap(payload: dict[str, Any], captured_at: datetime, request_path: str) -> dict[str, Any]:
    # The docstring.
    """Add capture metadata alongside the untouched API response."""
    # Build and return the wrapped record.
    return {
        # The moment we took the snapshot: this is what makes it a "vintage".
        "captured_at": captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        # Which request produced it, for traceability.
        "request_path": request_path,
        # The forecast rows exactly as the API sent them.
        "data": payload.get("data"),
    }


# Take both snapshots (national and regional).
def take_snapshots(
    # The API client, the capture time, and where to save.
    client: CarbonIntensityClient, captured_at: datetime, raw_dir: Path = config.RAW_DIR
# Returns a mapping of scope -> file written.
) -> dict[str, Path]:
    # The docstring.
    """Save national and regional fw48h forecasts; return the files written."""
    # Forecasts are half-hourly, so start from the current half-hour.
    start = floor_half_hour(captured_at)
    # Keep track of which files we wrote.
    written: dict[str, Path] = {}
    # Do the national forecast, then the regional one.
    for scope in ("national", "regional"):
        # Download the 48-hour forecast.
        payload = client.fetch_fw48h(scope, start)
        # Work out the file name.
        path = snapshot_path(scope, captured_at, raw_dir)
        # Wrap with metadata and save (refusing to save if empty).
        rows = save_records(path, wrap(payload, captured_at, f"{scope}/fw48h/{start:%Y-%m-%dT%H:%MZ}"))
        # Log what was saved.
        log.info("%s snapshot: %d periods -> %s", scope, rows, path)
        # Remember the file.
        written[scope] = path
    # Hand back the list of files.
    return written


# The function run from the command line.
def main() -> int:
    # The docstring.
    """Command-line entry point."""
    # Turn on INFO-level logging with timestamps.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Try to take the snapshots.
    try:
        # Use a real client and the current UTC time.
        take_snapshots(CarbonIntensityClient(), datetime.now(timezone.utc))
    # If the API failed or returned nothing...
    except (ApiError, EmptyResponseError) as exc:
        # ...log a clear error...
        log.error("snapshot failed: %s", exc)
        # ...and exit with code 1 so a scheduler notices.
        return 1
    # Success.
    return 0


# Only run main() when the file is run directly.
if __name__ == "__main__":
    # Pass main's result to the operating system as the exit code.
    sys.exit(main())
