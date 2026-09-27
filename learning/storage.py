# The module description.
"""Raw JSON storage: atomic writes and a guard against saving empty responses."""
# Allows modern type-hint syntax.
from __future__ import annotations

# Compresses and decompresses data (used for .gz snapshot files).
import gzip
# Converts Python data to JSON text.
import json
# Gives access to os.replace, which swaps a file into place in one step.
import os
# Represents file locations in a cross-platform way.
from pathlib import Path
# "Any" = any type.
from typing import Any


# A custom error meaning "the API gave us nothing, so we refused to save it".
class EmptyResponseError(ValueError):
    # The docstring.
    """Raised instead of writing a response that contains no records."""


# Write JSON safely, so a crash can never leave a half-written file behind.
def write_json_atomic(path: Path, payload: Any) -> None:
    # The docstring, with the reason this matters.
    """Write JSON via a temp file so a crash never leaves a half-written file.

    A half-written file would look "done" to the resumable backfill, so the
    rename-into-place step is what keeps resume safe.
    """
    # Create the folder (and any parent folders) if they don't exist yet.
    path.parent.mkdir(parents=True, exist_ok=True)
    # Choose a temporary name next to the real file, e.g. chunk.json.tmp.
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Turn the data into JSON text, then into bytes.
    data = json.dumps(payload).encode("utf-8")
    # If the file name ends in .gz, compress it first (snapshots are kept in git forever, so size matters).
    tmp.write_bytes(gzip.compress(data) if path.suffix == ".gz" else data)
    # Swap the finished temp file into the real name in one step: the file either exists complete, or not at all.
    os.replace(tmp, path)


# Read a raw file back, whether or not it is compressed.
def read_json(path: Path) -> Any:
    # The docstring.
    """Read a raw JSON file, compressed (.gz) or not."""
    # Read the file's bytes.
    raw = path.read_bytes()
    # Decompress if it is a .gz file, then turn the JSON text back into Python data.
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


# Save an API response, but only if it actually contains data.
def save_records(path: Path, payload: dict[str, Any], records_key: str = "data") -> int:
    # The docstring.
    """Save a response only if it contains records; return the record count."""
    # Look up the list of records (usually under "data"); if the payload isn't a dict, treat as nothing.
    records = payload.get(records_key) if isinstance(payload, dict) else None
    # An empty or missing list means there is nothing worth saving.
    if not records:
        # Refuse, so we never replace good data with an empty file.
        raise EmptyResponseError(f"refusing to write empty response to {path}")
    # Otherwise write it safely.
    write_json_atomic(path, payload)
    # Tell the caller how many records were saved (used in log messages).
    return len(records)
