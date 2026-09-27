# The module description: this file is the only place that knows how PV_Live works.
"""Client for Sheffield Solar PV_Live v4. All PV_Live specifics live here.

The API is under active development, so everything that depends on its
shape (paths, parameters, the meta/data tuple layout) is isolated in this module.
"""
# Allows modern type-hint syntax.
from __future__ import annotations

# Dates, lengths of time, and UTC.
from datetime import datetime, timedelta, timezone
# "Any" means the value could be of any type (JSON can hold anything).
from typing import Any

# Shared settings.
from pipeline import config
# The polite, retrying HTTP client.
from pipeline.http import ApiClient

# Extra columns to ask for: when each estimate was last revised, and installed solar capacity.
EXTRA_FIELDS: str = "updated_gmt,capacity_mwp"
# PV_Live uses GSP id 0 to mean "the whole of Great Britain".
NATIONAL_GSP_ID: int = 0


# Turn a datetime into the text format PV_Live expects.
def fmt(moment: datetime) -> str:
    # The docstring.
    """Format a datetime as ISO 8601 UTC, which PV_Live expects."""
    # Convert to UTC, then format like 2023-01-01T00:00:00Z.
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Convert PV_Live's compact table format into a list of labelled rows.
def rows_as_dicts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    # The docstring.
    """Turn the ``meta`` + ``data`` tuple format into dicts, never assuming column order."""
    # "meta" lists the column names, e.g. ["gsp_id", "datetime_gmt", "generation_mw", ...].
    columns = payload["meta"]
    # Pair each row's values with the column names, so we look things up by name, never by position.
    return [dict(zip(columns, row)) for row in payload["data"]]


# Pull the regional area ids out of the pes_list response.
def pes_ids(pes_list: dict[str, Any]) -> list[int]:
    # The docstring.
    """Return PES area ids from a ``pes_list`` payload, excluding 0 (national)."""
    # Read every row's pes_id, skip 0 (that's national, fetched separately), and sort them.
    return sorted(int(r["pes_id"]) for r in rows_as_dicts(pes_list) if int(r["pes_id"]) != 0)


# The client class used by the backfill.
class PVLiveClient:
    # The docstring.
    """Fetches national (GSP 0) and PES-area solar outturn estimates."""

    # The set-up method.
    def __init__(self, api: ApiClient | None = None) -> None:
        # The docstring.
        """Wrap a shared ``ApiClient`` (created if not supplied)."""
        # Use the client we were given (tests pass a fake one), or make a real one.
        self.api = api or ApiClient(config.PVLIVE_BASE_URL)

    # Ask PV_Live which regional areas exist.
    def fetch_pes_list(self) -> dict[str, Any]:
        # The docstring.
        """Fetch the list of PES (DNO licence area) ids and names."""
        # A simple GET to the pes_list endpoint.
        return self.api.get_json("pes_list")

    # Download solar estimates for one area and one time window.
    def fetch_range(self, entity: str, entity_id: int, start: datetime, end: datetime) -> dict[str, Any]:
        # The docstring.
        """Fetch one window for ``entity`` ('gsp' or 'pes') and its id."""
        # Only two kinds of area are supported; anything else is a bug in our code.
        if entity not in {"gsp", "pes"}:
            # Stop with a clear message.
            raise ValueError(f"unknown entity {entity!r}")
        # Refuse windows longer than our chunk size, before any request is sent.
        if end - start > timedelta(days=config.MAX_CHUNK_DAYS):
            # Stop with a clear message.
            raise ValueError(f"range {start}..{end} exceeds {config.MAX_CHUNK_DAYS} days")
        # Build the query-string parameters (?start=...&end=...&extra_fields=...).
        params = {"start": fmt(start), "end": fmt(end), "extra_fields": EXTRA_FIELDS}
        # Send the request, e.g. GET .../pes/16?start=...
        return self.api.get_json(f"{entity}/{entity_id}", params=params)
