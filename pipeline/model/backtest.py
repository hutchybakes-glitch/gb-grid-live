"""Rolling-origin backtest of the error-correction model against the official forecast.

    python -m pipeline.model.backtest

For each test month from ``FIRST_TEST_MONTH`` onwards, the model is trained on
all periods strictly before that month and scored on that month only, which
is how it would have been used in real time. Results go to DuckDB tables
``gold.gold_model_backtest`` and ``gold.gold_model_features``.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd

from pipeline import config
from pipeline.model import metrics
from pipeline.model.features import FEATURES, build_features

log = logging.getLogger("pipeline.model")

DB_PATH: Path = config.REPO_ROOT / "data" / "warehouse.duckdb"
FIRST_TEST_MONTH = "2024-01"
HORIZONS: dict[str, int] = {"1h_ahead": 2, "24h_ahead": 48}
PARAMS = dict(
    n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=42, verbose=-1,
)


@dataclass
class FoldResult:
    """Scores for one horizon and one test month."""

    horizon: str
    fold: str
    train_rows: int
    n: int
    mae_official: float
    mae_model: float
    mae_recent_error: float
    bias_official: float
    bias_model: float


def load_inputs(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """National forecast/actual plus national solar output, indexed by UTC period start."""
    df = con.sql(
        """select n.period_start_utc, n.forecast_gco2_kwh as forecast,
                  n.actual_gco2_kwh as actual, p.generation_mw as solar_mw
           from silver.silver_ci_national n
           left join silver.silver_pvlive p
             on p.area_id = 'gsp0' and p.period_start_utc = n.period_start_utc
           order by 1"""
    ).df()
    return df.set_index("period_start_utc")


def month_folds(index: pd.DatetimeIndex, first: str) -> list[str]:
    """Test months, as YYYY-MM strings, from ``first`` to the last month present."""
    months = sorted(set(index.strftime("%Y-%m")))
    return [m for m in months if m >= first]


def run_fold(feats: pd.DataFrame, month: str, horizon: str) -> tuple[FoldResult, lgb.LGBMRegressor] | None:
    """Train on everything before ``month`` and score on ``month``."""
    start = pd.Timestamp(f"{month}-01")
    end = start + pd.offsets.MonthBegin(1)
    usable = feats.dropna(subset=["target", "forecast"])
    train = usable[usable.index < start]
    test = usable[(usable.index >= start) & (usable.index < end)]
    if len(test) == 0 or len(train) < 1000:
        return None
    model = lgb.LGBMRegressor(**PARAMS)
    model.fit(train[FEATURES], train["target"])
    pred = test["forecast"] + model.predict(test[FEATURES])
    # A second, simpler baseline: shift the forecast by the latest known error.
    recent = test["forecast"] + test["err_lag"].fillna(0)
    a = test["actual"]
    return (
        FoldResult(
            horizon=horizon, fold=month, train_rows=len(train), n=len(test),
            mae_official=metrics.mae(a, test["forecast"]),
            mae_model=metrics.mae(a, pred),
            mae_recent_error=metrics.mae(a, recent),
            bias_official=metrics.bias(a, test["forecast"]),
            bias_model=metrics.bias(a, pred),
        ),
        model,
    )


def backtest(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run every horizon and fold; return (per-fold results, feature importances)."""
    rows: list[dict[str, object]] = []
    importances: list[dict[str, object]] = []
    for name, h in HORIZONS.items():
        feats = build_features(df, h)
        last_model = None
        weights: list[int] = []
        fold_rows: list[FoldResult] = []
        for month in month_folds(feats.dropna(subset=["target"]).index, FIRST_TEST_MONTH):
            out = run_fold(feats, month, name)
            if out is None:
                continue
            res, last_model = out
            fold_rows.append(res)
            weights.append(res.n)
            log.info("%s %s: official %.2f  model %.2f  (n=%d)", name, month, res.mae_official, res.mae_model, res.n)
        rows.extend(r.__dict__ for r in fold_rows)
        # Overall = period-weighted mean of monthly MAEs, i.e. MAE over all test periods.
        w = np.array(weights, dtype=float)
        rows.append({
            "horizon": name, "fold": "overall", "train_rows": None, "n": int(w.sum()),
            **{k: float(np.average([getattr(r, k) for r in fold_rows], weights=w))
               for k in ("mae_official", "mae_model", "mae_recent_error", "bias_official", "bias_model")},
        })
        if last_model is not None:
            gain = last_model.booster_.feature_importance(importance_type="gain")
            share = gain / gain.sum()
            importances.extend(
                {"horizon": name, "feature": f, "importance_share": float(s)} for f, s in zip(FEATURES, share)
            )
    return pd.DataFrame(rows), pd.DataFrame(importances)


def save(con: duckdb.DuckDBPyConnection, results: pd.DataFrame, importances: pd.DataFrame) -> None:
    """Replace the gold model tables."""
    results = results.assign(built_at_utc=datetime.now(timezone.utc).replace(tzinfo=None))
    con.sql("create schema if not exists gold")
    con.register("results_df", results)
    con.register("imp_df", importances)
    con.sql("create or replace table gold.gold_model_backtest as select * from results_df")
    con.sql("create or replace table gold.gold_model_features as select * from imp_df")


def main(db_path: Path = DB_PATH) -> int:
    """Load, backtest and save."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    con = duckdb.connect(str(db_path))
    try:
        results, importances = backtest(load_inputs(con))
        save(con, results, importances)
    finally:
        con.close()
    overall = results[results["fold"] == "overall"]
    for _, r in overall.iterrows():
        log.info(
            "%s overall MAE: official %.2f | model %.2f | official+recent error %.2f",
            r["horizon"], r["mae_official"], r["mae_model"], r["mae_recent_error"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
