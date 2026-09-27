"""NESO Historic Demand Data (one CSV per year) from the NESO Data Portal.

Licence: NESO Open Data Licence. No key needed. Used for the hidden-solar
story: rooftop solar that the grid cannot see shows up as lower national demand.

    python -m pipeline.ingest.neso_demand
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline import config
from pipeline.http import ApiClient
from pipeline.storage import write_json_atomic

log = logging.getLogger("pipeline.neso_demand")

BASE_URL = "https://api.neso.energy/api/3/action"
DATASET_ID = "historic-demand-data"
FIRST_YEAR = config.BACKFILL_START.year


def raw_path(year: int, raw_dir: Path = config.RAW_DIR) -> Path:
    """Where one year's CSV is stored."""
    return raw_dir / "neso_demand" / str(year) / f"demanddata_{year}.csv"


def years_to_fetch(now: datetime, raw_dir: Path = config.RAW_DIR) -> list[int]:
    """Missing years, plus the current year (still being filled in) and, in
    January, the previous year (its last days are finalised late)."""
    wanted: list[int] = []
    for year in range(FIRST_YEAR, now.year + 1):
        recent = year == now.year or (year == now.year - 1 and now.month == 1)
        if recent or not raw_path(year, raw_dir).exists():
            wanted.append(year)
    return wanted


def resource_urls(api: ApiClient) -> dict[int, str]:
    """Map year -> CSV download URL, read from the dataset listing (never guessed)."""
    listing = api.get_json("package_show", params={"id": DATASET_ID})
    urls: dict[int, str] = {}
    for res in listing["result"]["resources"]:
        name = res.get("name", "")
        if res.get("format", "").upper() == "CSV" and name.startswith("Historic Demand Data "):
            tail = name.rsplit(" ", 1)[-1]
            if tail.isdigit():
                urls[int(tail)] = res["url"]
    return urls


def fetch_year(api: ApiClient, url: str) -> str:
    """Download one CSV as text (with the shared retries and rate limit)."""
    return api.get_text(url)


def save_csv(path: Path, text: str) -> int:
    """Save a CSV atomically if it has at least one data row; return the row count."""
    rows = max(0, len(text.strip().splitlines()) - 1)
    if rows == 0:
        raise ValueError(f"refusing to write empty CSV to {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    # newline="" writes the text exactly as received. The default would turn
    # the server's CRLF line endings into CR CR LF on Windows and corrupt the CSV.
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)
    return rows


def main(raw_dir: Path = config.RAW_DIR) -> int:
    """Fetch any missing or recent years; return 1 if any year failed."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    api = ApiClient(BASE_URL)
    failed = 0
    try:
        urls = resource_urls(api)
        write_json_atomic(raw_dir / "neso_demand" / "resources.json", {"data": [{"year": y, "url": u} for y, u in sorted(urls.items())]})
        for year in years_to_fetch(datetime.now(timezone.utc), raw_dir):
            if year not in urls:
                log.warning("no demand CSV listed for %d yet", year)
                continue
            try:
                rows = save_csv(raw_path(year, raw_dir), fetch_year(api, urls[year]))
                log.info("neso_demand %d: %d rows", year, rows)
            except Exception as exc:  # keep going: other years are independent
                failed += 1
                log.error("neso_demand %d failed: %s", year, exc)
    finally:
        api.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
