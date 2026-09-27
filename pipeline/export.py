"""Export small JSON files from gold tables for the static site.

    python -m pipeline.export

Each file feeds one page or chart. Times are ISO 8601 UTC strings ending in Z;
the site converts to UK local time for display.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import duckdb

from pipeline import config

log = logging.getLogger("pipeline.export")

DB_PATH: Path = config.REPO_ROOT / "data" / "warehouse.duckdb"
OUT_DIR: Path = config.REPO_ROOT / "web" / "public" / "data"
TEST_RESULTS_PATH: Path = config.REPO_ROOT / "data" / "dbt_test_results.json"


def to_json_value(value: Any) -> Any:
    """Make DuckDB values JSON-safe; naive timestamps from the warehouse are UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, list):
        return [to_json_value(v) for v in value]
    if isinstance(value, dict):
        return {k: to_json_value(v) for k, v in value.items()}
    return value


def query(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    """Run a query and return rows as JSON-safe dicts."""
    rel = con.sql(sql)
    cols = rel.columns
    return [{c: to_json_value(v) for c, v in zip(cols, row)} for row in rel.fetchall()]


def write(name: str, payload: Any, out_dir: Path = OUT_DIR) -> None:
    """Write one compact JSON file, refusing to write an empty dataset."""
    if payload in (None, [], {}):
        raise ValueError(f"refusing to export empty {name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    log.info("wrote %s (%d bytes)", path.name, path.stat().st_size)


def export_regions(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Region list for the selector and map."""
    return query(con, "select region_id, short_name, dno_region, region_type from dim.dim_region order by region_id")


def export_region_now(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Current forecast per region with mix."""
    return query(
        con,
        """select region_id, short_name, period_start_utc, forecast_gco2_kwh, intensity_index,
                  gb_forecast_gco2_kwh, diff_vs_gb, top_fuel, generation_mix, captured_at
           from gold.gold_region_now order by region_id""",
    )


def export_region_48h(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """48h forecast as {captured_at, regions: {id: [[t, gCO2, band], ...]}} to keep it small."""
    rows = query(
        con,
        """select region_id, period_start_utc, forecast_gco2_kwh, intensity_index, captured_at
           from gold.gold_region_48h order by region_id, period_start_utc""",
    )
    regions: dict[str, list[list[Any]]] = {}
    for r in rows:
        regions.setdefault(str(r["region_id"]), []).append(
            [r["period_start_utc"], r["forecast_gco2_kwh"], r["intensity_index"]]
        )
    return {"captured_at": rows[0]["captured_at"] if rows else None, "regions": regions}


def export_pipeline_health(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Per-source health rows, gap summary and dbt test results."""
    tests = json.loads(TEST_RESULTS_PATH.read_text(encoding="utf-8")) if TEST_RESULTS_PATH.exists() else None
    return {
        "sources": query(con, "select * from gold.gold_pipeline_health order by source"),
        "gap_days": query(
            con,
            """select source, utc_date, count(*) as missing_half_hours, count(distinct area_id) as areas
               from gold.gold_data_gaps group by all order by utc_date desc, source limit 60""",
        ),
        "tests": tests,
    }


def export_trust(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Official forecast accuracy, snapshot accuracy and the model backtest."""
    return {
        "accuracy": query(con, "select * from gold.gold_forecast_accuracy order by grouping, group_key"),
        "snapshot_accuracy": query(con, "select * from gold.gold_snapshot_accuracy order by min_lead_hours"),
        "snapshot_days": query(
            con,
            """select count(distinct cast(captured_at as date)) as days, min(captured_at) as first, max(captured_at) as last
               from bronze.bronze_forecast_snapshots where scope = 'national'""",
        )[0],
        "backtest": query(con, "select * exclude (built_at_utc) from gold.gold_model_backtest order by horizon, fold"),
        "features": query(con, "select * from gold.gold_model_features order by horizon, importance_share desc"),
    }


def export_explore(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Heatmap, region league, solar profile and insight numbers."""
    return {
        "heatmap": query(con, "select local_month, local_hour, avg_actual_gco2_kwh, n from gold.gold_heatmap_hour_month"),
        "league": query(con, "select * from gold.gold_region_league order by window_days, rank"),
        "solar": query(con, "select * from gold.gold_solar_vs_demand order by season, slot"),
        "solar_peak": query(
            con,
            """select arg_max(period_start_utc, generation_mw) as at_utc, max(generation_mw) as mw
               from silver.silver_pvlive where area_id = 'gsp0'""",
        )[0],
        "insights": query(con, "select * from gold.gold_insights order by card"),
    }


EXPORTS: dict[str, Callable[[duckdb.DuckDBPyConnection], Any]] = {
    "regions.json": export_regions,
    "region_now.json": export_region_now,
    "region_48h.json": export_region_48h,
    "pipeline_health.json": export_pipeline_health,
    "trust.json": export_trust,
    "explore.json": export_explore,
}


def main(db_path: Path = DB_PATH, out_dir: Path = OUT_DIR, read_only: bool = True) -> int:
    """Write every export; a failure in one export stops the run before the meta file is updated.

    ``read_only=False`` is needed when called in the same process as dbt,
    because DuckDB refuses a second connection to a file with different settings.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    con = duckdb.connect(str(db_path), read_only=read_only)
    try:
        for name, fn in EXPORTS.items():
            write(name, fn(con), out_dir)
        latest = query(con, "select max(captured_at) as t from bronze.bronze_forecast_snapshots")[0]["t"]
        write(
            "meta.json",
            {"exported_at": to_json_value(datetime.now(timezone.utc)), "data_last_updated": latest},
            out_dir,
        )
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
