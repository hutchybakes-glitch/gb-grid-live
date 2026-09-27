"""Client for the NESO Carbon Intensity API (https://api.carbonintensity.org.uk)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pipeline import config
from pipeline.http import ApiClient

# Source name -> path template for ranged historical requests.
RANGE_ENDPOINTS: dict[str, str] = {
    "ci_national": "intensity/{start}/{end}",
    "ci_generation": "generation/{start}/{end}",
    "ci_regional": "regional/intensity/{start}/{end}",
}

FW48H_ENDPOINTS: dict[str, str] = {
    "national": "intensity/{start}/fw48h",
    "regional": "regional/intensity/{start}/fw48h",
}


def fmt(moment: datetime) -> str:
    """Format a datetime in the API's ``YYYY-MM-DDThh:mmZ`` style."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def range_path(endpoint: str, start: datetime, end: datetime) -> str:
    """Build a ranged path, refusing anything over the API's 14-day limit."""
    if end - start > timedelta(days=config.MAX_CHUNK_DAYS):
        raise ValueError(f"range {start}..{end} exceeds {config.MAX_CHUNK_DAYS} days")
    return RANGE_ENDPOINTS[endpoint].format(start=fmt(start), end=fmt(end))


class CarbonIntensityClient:
    """Fetches national, generation and regional data from the Carbon Intensity API."""

    def __init__(self, api: ApiClient | None = None) -> None:
        """Wrap a shared ``ApiClient`` (created if not supplied)."""
        self.api = api or ApiClient(config.CI_BASE_URL)

    def fetch_range(self, endpoint: str, start: datetime, end: datetime) -> dict[str, Any]:
        """Fetch one window of at most 14 days for ``endpoint`` (a RANGE_ENDPOINTS key)."""
        return self.api.get_json(range_path(endpoint, start, end))

    def fetch_fw48h(self, scope: str, start: datetime) -> dict[str, Any]:
        """Fetch the 48-hour forward forecast; ``scope`` is 'national' or 'regional'."""
        return self.api.get_json(FW48H_ENDPOINTS[scope].format(start=fmt(start)))

    def fetch_factors(self) -> dict[str, Any]:
        """Fetch the gCO2/kWh factor for each fuel type."""
        return self.api.get_json("intensity/factors")
