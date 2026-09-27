"""Client for Sheffield Solar PV_Live v4. All PV_Live specifics live here.

The API is under active development, so everything that depends on its
shape (paths, parameters, the meta/data tuple layout) is isolated in this module.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pipeline import config
from pipeline.http import ApiClient

EXTRA_FIELDS: str = "updated_gmt,capacity_mwp"
NATIONAL_GSP_ID: int = 0


def fmt(moment: datetime) -> str:
    """Format a datetime as ISO 8601 UTC, which PV_Live expects."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows_as_dicts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn the ``meta`` + ``data`` tuple format into dicts, never assuming column order."""
    columns = payload["meta"]
    return [dict(zip(columns, row)) for row in payload["data"]]


def pes_ids(pes_list: dict[str, Any]) -> list[int]:
    """Return PES area ids from a ``pes_list`` payload, excluding 0 (national)."""
    return sorted(int(r["pes_id"]) for r in rows_as_dicts(pes_list) if int(r["pes_id"]) != 0)


class PVLiveClient:
    """Fetches national (GSP 0) and PES-area solar outturn estimates."""

    def __init__(self, api: ApiClient | None = None) -> None:
        """Wrap a shared ``ApiClient`` (created if not supplied)."""
        self.api = api or ApiClient(config.PVLIVE_BASE_URL)

    def fetch_pes_list(self) -> dict[str, Any]:
        """Fetch the list of PES (DNO licence area) ids and names."""
        return self.api.get_json("pes_list")

    def fetch_range(self, entity: str, entity_id: int, start: datetime, end: datetime) -> dict[str, Any]:
        """Fetch one window for ``entity`` ('gsp' or 'pes') and its id."""
        if entity not in {"gsp", "pes"}:
            raise ValueError(f"unknown entity {entity!r}")
        if end - start > timedelta(days=config.MAX_CHUNK_DAYS):
            raise ValueError(f"range {start}..{end} exceeds {config.MAX_CHUNK_DAYS} days")
        params = {"start": fmt(start), "end": fmt(end), "extra_fields": EXTRA_FIELDS}
        return self.api.get_json(f"{entity}/{entity_id}", params=params)
