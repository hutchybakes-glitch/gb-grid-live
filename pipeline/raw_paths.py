"""Naming rules for raw files, shared by the backfill, snapshot and summary."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pipeline import config
from pipeline.chunks import Chunk


def stamp(moment: datetime) -> str:
    """Compact UTC timestamp without colons, which Windows does not allow in file names."""
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%MZ")


def chunk_path(source: str, chunk: Chunk, raw_dir: Path = config.RAW_DIR) -> Path:
    """Where the raw response for one source and chunk is stored."""
    folder = raw_dir / source / chunk.start.strftime("%Y-%m-%d")
    return folder / f"{source}_{stamp(chunk.start)}_{stamp(chunk.end)}.json"


def stale_siblings(path: Path) -> list[Path]:
    """Other files for the same source and chunk start but a different end.

    The newest chunk is usually cut short at "today", so tomorrow's run
    fetches a longer version of it; the shorter, older file is then redundant.
    """
    prefix = path.stem.rsplit("_", 1)[0]
    if not path.parent.exists():
        return []
    return [p for p in path.parent.glob(f"{prefix}_*.json") if p != path]
