"""Export helpers: UTC formatting and the empty-data guard."""
from __future__ import annotations

from datetime import datetime

import duckdb
import pytest

from pipeline import export


def test_naive_warehouse_timestamps_are_labelled_utc() -> None:
    assert export.to_json_value(datetime(2026, 3, 29, 1, 30)) == "2026-03-29T01:30:00Z"


def test_aware_timestamps_are_converted_to_utc() -> None:
    from zoneinfo import ZoneInfo

    bst = datetime(2026, 6, 1, 13, 0, tzinfo=ZoneInfo("Europe/London"))
    assert export.to_json_value(bst) == "2026-06-01T12:00:00Z"


def test_nested_values_and_floats() -> None:
    assert export.to_json_value([{"perc": 12.34567}]) == [{"perc": 12.346}]


def test_empty_export_is_refused(tmp_path) -> None:
    with pytest.raises(ValueError):
        export.write("x.json", [], tmp_path)
    assert not (tmp_path / "x.json").exists()


def test_query_returns_json_safe_dicts() -> None:
    con = duckdb.connect()
    rows = export.query(con, "select 1 as a, timestamp '2026-01-01 00:00' as t")
    assert rows == [{"a": 1, "t": "2026-01-01T00:00:00Z"}]
