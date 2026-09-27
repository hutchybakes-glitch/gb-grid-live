"""Metrics and leakage checks for the error-correction model."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.model import metrics
from pipeline.model.backtest import month_folds, run_fold
from pipeline.model.features import FEATURES, build_features


def test_mae_known_values() -> None:
    # errors +10, -20, 0 -> MAE 10
    assert metrics.mae([110, 100, 90], [100, 120, 90]) == pytest.approx(10.0)
    assert metrics.bias([110, 100, 90], [100, 120, 90]) == pytest.approx(-10 / 3)
    assert metrics.rmse([110, 100, 90], [100, 120, 90]) == pytest.approx(np.sqrt(500 / 3))


def test_metrics_refuse_missing_actuals() -> None:
    with pytest.raises(ValueError):
        metrics.mae([1.0, float("nan")], [1.0, 2.0])
    with pytest.raises(ValueError):
        metrics.mae([], [])


def frame(n: int = 200, start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="30min", name="period_start_utc")
    rng = np.random.default_rng(0)
    forecast = 150 + 30 * np.sin(np.arange(n) / 8)
    return pd.DataFrame(
        {"forecast": forecast, "actual": forecast + rng.normal(0, 5, n), "solar_mw": rng.uniform(0, 5000, n)},
        index=idx,
    )


@pytest.mark.parametrize("horizon", [2, 48])
def test_no_feature_uses_information_after_the_cutoff(horizon: int) -> None:
    """Poison every actual and solar value after a cut-off; features before cut-off + horizon must not change."""
    df = frame()
    base = build_features(df, horizon)
    cut = df.index[120]
    poisoned = df.copy()
    poisoned.loc[poisoned.index > cut, ["actual", "solar_mw"]] = 1e9
    after = build_features(poisoned, horizon)
    # Period t may use information up to t - horizon, so periods up to cut + horizon slots are unaffected.
    safe = base.index <= cut + pd.Timedelta(minutes=30 * horizon)
    feature_cols = [c for c in FEATURES if c != "forecast"]
    pd.testing.assert_frame_equal(base.loc[safe, feature_cols], after.loc[safe, feature_cols])


def test_missing_period_does_not_shift_wrong_row() -> None:
    df = frame(10).drop(index=frame(10).index[5])  # remove one half-hour
    f = build_features(df, 1)
    # The period after the gap must have NaN lag, not the error from two slots back.
    assert np.isnan(f.loc[df.index[5], "err_lag"])


def test_rolling_origin_trains_only_on_the_past() -> None:
    df = frame(48 * 100, start="2023-11-01")  # 1 Nov to 8 Feb: all of January included
    feats = build_features(df, 2)
    res, _ = run_fold(feats, "2024-01", "1h_ahead")
    train_rows_before_jan = feats.dropna(subset=["target", "forecast"]).loc[: "2023-12-31 23:30"].shape[0]
    assert res.train_rows == train_rows_before_jan
    assert res.n == 48 * 31


def test_month_folds() -> None:
    idx = pd.date_range("2023-11-01", "2024-02-10", freq="1D")
    assert month_folds(idx, "2024-01") == ["2024-01", "2024-02"]
