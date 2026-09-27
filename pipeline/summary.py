"""Print files, row counts and date coverage per raw source.

    python -m pipeline.summary
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline import config
from pipeline.storage import read_json


@dataclass
class SourceSummary:
    """Totals for one raw source folder."""

    files: int = 0
    rows: int = 0
    first: str | None = None
    last: str | None = None

    def add(self, rows: int, times: list[str]) -> None:
        """Fold one file's counts into the totals."""
        self.files += 1
        self.rows += rows
        if times:
            lo, hi = min(times), max(times)
            self.first = lo if self.first is None else min(self.first, lo)
            self.last = hi if self.last is None else max(self.last, hi)


def period_times(payload: dict[str, Any]) -> list[str]:
    """Extract period timestamps from either source's format.

    CI rows are dicts with ``from``; PV_Live rows are tuples described by ``meta``.
    Both are ISO strings in UTC, so string comparison sorts them correctly.
    """
    rows = payload.get("data") or []
    if "meta" in payload:
        if "datetime_gmt" not in payload["meta"]:
            return []
        idx = payload["meta"].index("datetime_gmt")
        return [row[idx] for row in rows]
    return [row["from"] for row in rows if isinstance(row, dict) and "from" in row]


def summarise(raw_dir: Path = config.RAW_DIR) -> dict[str, SourceSummary]:
    """Walk ``raw_dir`` and total up every source folder."""
    result: dict[str, SourceSummary] = {}
    for source_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        summary = SourceSummary()
        for path in sorted([*source_dir.rglob("*.json"), *source_dir.rglob("*.json.gz")]):
            payload = read_json(path)
            summary.add(len(payload.get("data") or []), period_times(payload))
        result[source_dir.name] = summary
    return result


def main() -> None:
    """Print the summary table."""
    if not config.RAW_DIR.exists():
        print(f"No raw data yet at {config.RAW_DIR}")
        return
    print(f"{'source':<20}{'files':>7}{'rows':>10}  {'first period':<22}{'last period':<22}")
    for name, s in summarise().items():
        print(f"{name:<20}{s.files:>7}{s.rows:>10}  {s.first or '-':<22}{s.last or '-':<22}")


if __name__ == "__main__":
    main()
