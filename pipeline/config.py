"""Central settings for ingestion: URLs, dates, paths and politeness limits."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
RAW_DIR: Path = REPO_ROOT / "data" / "raw"

CI_BASE_URL: str = "https://api.carbonintensity.org.uk"
PVLIVE_BASE_URL: str = "https://api.pvlive.uk/pvlive/api/v4"

BACKFILL_START: datetime = datetime(2023, 1, 1, tzinfo=timezone.utc)

# The Carbon Intensity API rejects ranges over 14 days; we reuse the same
# window for PV_Live so both sources share one resumable chunk scheme.
MAX_CHUNK_DAYS: int = 14
# The regional endpoint rejects an exact 14-day window as "greater than 14
# days" (the national one accepts it), so regional uses 13-day chunks.
REGIONAL_CHUNK_DAYS: int = 13

# Chunks ending within this many days of the run are refetched every run,
# because recent actuals and PV_Live estimates are still being filled in.
REFRESH_RECENT_DAYS: int = 2

# Politeness: at most one request per second across the whole process.
MIN_SECONDS_BETWEEN_REQUESTS: float = 1.0
MAX_RETRIES: int = 5
REQUEST_TIMEOUT_SECONDS: float = 60.0
USER_AGENT: str = "gb-grid-live/0.1 (independent portfolio project)"
