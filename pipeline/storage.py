"""Raw JSON storage: atomic writes and a guard against saving empty responses."""
from __future__ import annotations

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
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def save_records(path: Path, payload: dict[str, Any], records_key: str = "data") -> int:
    """Save a response only if it contains records; return the record count."""
    records = payload.get(records_key) if isinstance(payload, dict) else None
    if not records:
        raise EmptyResponseError(f"refusing to write empty response to {path}")
    write_json_atomic(path, payload)
    return len(records)
