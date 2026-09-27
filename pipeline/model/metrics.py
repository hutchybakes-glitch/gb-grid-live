"""Forecast error metrics. Error is defined as actual - forecast throughout."""
from __future__ import annotations

from typing import Sequence

import numpy as np


def _pair(actual: Sequence[float], forecast: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    """Convert to float arrays, checking lengths match and there is data."""
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    if a.shape != f.shape:
        raise ValueError(f"length mismatch: {a.shape} vs {f.shape}")
    if a.size == 0:
        raise ValueError("no values to score")
    if np.isnan(a).any() or np.isnan(f).any():
        # A null actual is "not yet measured", never zero: callers must drop it.
        raise ValueError("NaN in inputs; drop missing actuals before scoring")
    return a, f


def mae(actual: Sequence[float], forecast: Sequence[float]) -> float:
    """Mean absolute error."""
    a, f = _pair(actual, forecast)
    return float(np.mean(np.abs(a - f)))


def rmse(actual: Sequence[float], forecast: Sequence[float]) -> float:
    """Root mean squared error."""
    a, f = _pair(actual, forecast)
    return float(np.sqrt(np.mean((a - f) ** 2)))


def bias(actual: Sequence[float], forecast: Sequence[float]) -> float:
    """Mean of (actual - forecast): positive means the forecast runs low."""
    a, f = _pair(actual, forecast)
    return float(np.mean(a - f))
