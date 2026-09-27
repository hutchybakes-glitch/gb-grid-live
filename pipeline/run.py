"""Run the whole pipeline end to end.

    python -m pipeline.run                 # ingest, snapshot, dbt build
    python -m pipeline.run --skip-ingest   # rebuild the warehouse from raw files only
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from pipeline import backfill, config, snapshot

log = logging.getLogger("pipeline.run")

TRANSFORM_DIR: Path = config.REPO_ROOT / "transform"
DB_PATH: Path = config.REPO_ROOT / "data" / "warehouse.duckdb"
TEST_RESULTS_PATH: Path = config.REPO_ROOT / "data" / "dbt_test_results.json"


def dbt_env() -> None:
    """Point dbt at absolute paths so it works from any working directory."""
    os.environ["GBGL_RAW_DIR"] = str(config.RAW_DIR)
    os.environ["GBGL_DB_PATH"] = str(DB_PATH)


def run_dbt(args: list[str]) -> Any:
    """Invoke dbt in-process and return its result object."""
    from dbt.cli.main import dbtRunner  # imported lazily: dbt is slow to import

    dbt_env()
    base = ["--project-dir", str(TRANSFORM_DIR), "--profiles-dir", str(TRANSFORM_DIR)]
    return dbtRunner().invoke([*args, *base])


def summarise_tests(result: Any) -> dict[str, Any]:
    """Count test outcomes from a dbt build and keep a per-test list for the site."""
    tests = []
    for r in result.result or []:
        node = r.node
        if node.resource_type != "test":
            continue
        tests.append({"name": node.name, "status": str(r.status), "failures": r.failures})
    counts: dict[str, int] = {}
    for t in tests:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    return {"counts": counts, "tests": tests}


def main(argv: list[str] | None = None) -> int:
    """Ingest (optional), snapshot (optional), then build and test every dbt model."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-ingest", action="store_true", help="do not call the APIs")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    ingest_ok = True
    if not args.skip_ingest:
        # An ingest failure is reported but does not stop the build: the
        # warehouse is rebuilt from whatever good raw data is already on disk.
        ingest_ok = backfill.main([]) == 0
        ingest_ok = snapshot.main() == 0 and ingest_ok

    result = run_dbt(["build"])
    summary = summarise_tests(result)
    TEST_RESULTS_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("dbt build success=%s; tests: %s", result.success, summary["counts"])
    if not ingest_ok:
        log.error("ingestion had failures; see messages above")
    return 0 if (result.success and ingest_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
