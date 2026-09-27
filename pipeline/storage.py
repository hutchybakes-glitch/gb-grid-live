"""Raw JSON storage: atomic writes and a guard against saving empty responses."""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import Any


class EmptyResponseError(ValueError):
    """Raised instead of writing a response that contains no records."""


def write_json_atomic(path: Path, payload: Any) -> None:
    """Write JSON via a temp file so a crash never leaves a half-written file.

    A half-written file would look "done" to the resumable backfill, so the
    rename-into-place step is what keeps resume safe.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload).encode("utf-8")
    # A .gz name means "store compressed": snapshots are kept in git forever.
    tmp.write_bytes(gzip.compress(data) if path.suffix == ".gz" else data)
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    """Read a raw JSON file, compressed (.gz) or not."""
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def save_records(path: Path, payload: dict[str, Any], records_key: str = "data") -> int:
    """Save a response only if it contains records; return the record count."""
    records = payload.get(records_key) if isinstance(payload, dict) else None
    if not records:
        raise EmptyResponseError(f"refusing to write empty response to {path}")
    write_json_atomic(path, payload)
    return len(records)
