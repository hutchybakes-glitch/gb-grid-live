"""NESO demand ingestion: which years to fetch, safe saving, listing parse."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from pipeline.ingest import neso_demand


def test_years_to_fetch_skips_complete_past_years(tmp_path) -> None:
    for y in (2023, 2024):
        p = neso_demand.raw_path(y, tmp_path)
        p.parent.mkdir(parents=True)
        p.write_text("h\n1\n")
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    assert neso_demand.years_to_fetch(now, tmp_path) == [2025, 2026]


def test_previous_year_refetched_in_january(tmp_path) -> None:
    for y in (2023, 2024, 2025):
        p = neso_demand.raw_path(y, tmp_path)
        p.parent.mkdir(parents=True)
        p.write_text("h\n1\n")
    assert neso_demand.years_to_fetch(datetime(2026, 1, 5, tzinfo=timezone.utc), tmp_path) == [2025, 2026]


def test_save_csv_keeps_line_endings_exactly(tmp_path) -> None:
    # Regression: text mode on Windows once turned \r\n into \r\r\n and broke parsing.
    path = tmp_path / "x.csv"
    assert neso_demand.save_csv(path, "A,B\r\n1,2\r\n") == 1
    assert path.read_bytes() == b"A,B\r\n1,2\r\n"


def test_save_csv_refuses_header_only(tmp_path) -> None:
    with pytest.raises(ValueError):
        neso_demand.save_csv(tmp_path / "x.csv", "A,B\r\n")


def test_resource_urls_read_from_listing(make_api) -> None:
    listing = {"result": {"resources": [
        {"name": "Historic Demand Data 2025", "format": "CSV", "url": "https://x/2025.csv"},
        {"name": "Historic Demand Data 2026", "format": "CSV", "url": "https://x/2026.csv"},
        {"name": "Frequently Asked Questions (FAQ)", "format": "DOC", "url": "https://x/faq.docx"},
    ]}}
    api, _ = make_api("https://api.neso.energy/api/3/action", lambda r: httpx.Response(200, json=listing))
    assert neso_demand.resource_urls(api) == {2025: "https://x/2025.csv", 2026: "https://x/2026.csv"}
