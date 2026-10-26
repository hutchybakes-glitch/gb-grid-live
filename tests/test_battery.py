"""Tests for the battery pipeline: optimiser rules, clock changes, the tariff formula and no look-ahead."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from pipeline.battery import forecast, optimise, settings, sources, store, tariff

RNG = np.random.default_rng(42)


def _prices(n: int = 48, negative: bool = False) -> np.ndarray:
    """A plausible day of prices in £/kWh: cheap night, dear evening, optional negative hours."""
    base = 0.08 + 0.06 * np.sin(np.linspace(0, 2 * np.pi, n)) + RNG.normal(0, 0.02, n)
    base[32:38] += 0.25
    if negative:
        base[4:10] = -0.15
    return base


@pytest.mark.parametrize("hours", settings.HOURS_OPTIONS)
@pytest.mark.parametrize("eff", settings.EFFICIENCY_OPTIONS)
@pytest.mark.parametrize("negative", [False, True])
def test_schedule_respects_physics(hours: int, eff: int, negative: bool) -> None:
    """Charge level stays within 0..1, power within limits, never charge and use at once, day ends where it began."""
    p = _prices(negative=negative)
    s = optimise.best_schedule(p, hours, eff)
    assert s.level.min() >= -1e-9 and s.level.max() <= 1 + 1e-9
    assert s.charge.max() <= 1 / hours + 1e-9 and s.use.max() <= 1 / hours + 1e-9
    assert not np.any(np.minimum(s.charge, s.use) > 1e-6)
    eta = (eff / 100) ** 0.5
    net_energy = np.sum(eta * s.charge - s.use / eta) * optimise.DT
    assert abs(net_energy) < 1e-6


@pytest.mark.parametrize("n", [46, 48, 50])
def test_hindsight_beats_timer_and_forecast(n: int) -> None:
    """With perfect hindsight the optimiser can't do worse than any other plan (counting its wear cost)."""
    wear = settings.WEAR_PENCE_PER_KWH / 100
    hours_local = np.arange(n) // 2 % 24
    for _ in range(20):
        actual = _prices(n)
        guess = actual + RNG.normal(0, 0.05, n)
        best = optimise.settle(optimise.best_schedule(actual, 2, 90), actual, np.zeros(n))
        for other in (optimise.best_schedule(guess, 2, 90), optimise.timer_schedule(hours_local, 2, 90)):
            r = optimise.settle(other, actual, np.zeros(n))
            assert best["SavingPerKWh"] - wear * best["CyclesPerKWh"] >= r["SavingPerKWh"] - wear * r["CyclesPerKWh"] - 1e-9


def test_timer_ends_empty() -> None:
    """The timer only stores what it can use in the evening window."""
    for hours in settings.HOURS_OPTIONS:
        s = optimise.timer_schedule(np.repeat(np.arange(24), 2), hours, 90)
        assert s.level[-1] == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize("day,periods", [(date(2026, 3, 29), 46), (date(2026, 10, 25), 50), (date(2026, 10, 26), 48)])
def test_local_day_lengths(day: date, periods: int) -> None:
    """Clock-change days have 46 or 50 half-hours."""
    a, b = sources.local_day_bounds(day)
    assert (b - a).total_seconds() / 1800 == periods


def test_tariff_formula_and_cap() -> None:
    """Multiplier x wholesale p/kWh + peak charge, plus VAT, capped at 100p."""
    out = tariff.tariff_pence(np.array([100.0, 100.0, 2000.0, -50.0]), np.array([0, 1, 1, 0]), 2.0, 12.0)
    assert out[0] == pytest.approx(21.0)
    assert out[1] == pytest.approx(33.6)
    assert out[2] == 100.0
    assert out[3] == pytest.approx(-10.5)


def test_decision_cutoff_hides_later_forecasts() -> None:
    """A forecast published after 17:15 UTC the day before is never used for that day."""
    day = date(2026, 1, 15)
    t = pd.Timestamp("2026-01-15T12:00Z")
    raw = pd.DataFrame({
        "period_start_utc": [t, t],
        "publish_utc": [pd.Timestamp("2026-01-14T16:45Z"), pd.Timestamp("2026-01-14T20:00Z")],
        "quantity": [1.0, 2.0],
    })
    kept = sources._keep_known_at_decision(raw)
    assert list(kept["quantity"]) == [1.0]
    assert sources.decision_cutoff(day) == pd.Timestamp("2026-01-14T17:15Z")


def test_features_have_no_look_ahead() -> None:
    """lag_2d for day D comes from D-2; the 7-day level ends two days before."""
    start, _ = sources.local_day_bounds(date(2026, 1, 1))
    idx = pd.date_range(start, periods=48 * 20, freq="30min", tz="UTC")
    hh = pd.DataFrame({"period_start_utc": idx, "price": np.arange(len(idx), dtype=float),
                       "wind_mw": 1.0, "solar_mw": 0.0, "demand_mw": 2.0})
    f = forecast.build_features(hh)
    row = f.iloc[48 * 10 + 5]
    assert row["lag_2d"] == row["price"] - 96
    assert row["lag_7d"] == row["price"] - 336
    day_means = hh.groupby(f["local_date"])["price"].mean()
    d = row["local_date"]
    expected = day_means.loc[[d - timedelta(days=k) for k in range(2, 9)]].mean()
    assert row["level_7d"] == pytest.approx(expected)


def test_store_runs_groups_consecutive_days() -> None:
    """Days are fetched in consecutive runs."""
    d = date(2026, 1, 1)
    days = [d, d + timedelta(1), d + timedelta(2), d + timedelta(5)]
    assert store.runs(days) == [(d, d + timedelta(2)), (d + timedelta(5), d + timedelta(5))]


class _FakeClient:
    """Returns two overlapping DGWS chunks, like the real API does at chunk boundaries."""

    def __init__(self) -> None:
        self.calls = 0

    def get_json(self, path: str, params: dict) -> dict:
        self.calls += 1
        rows = []
        for start in ("2026-01-14T23:30:00Z", "2026-01-15T00:00:00Z"):
            for psr, q in (("Wind Onshore", 100.0), ("Wind Offshore", 200.0), ("Solar", 5.0)):
                rows.append({"startTime": start, "publishTime": "2026-01-14T16:45:00Z", "psrType": psr, "quantity": q})
        return {"data": rows}


def test_wind_solar_overlap_not_double_counted() -> None:
    """The same half-hour returned by two chunks is counted once."""
    out = sources.wind_solar_forecast(_FakeClient(), date(2026, 1, 15), date(2026, 1, 15))
    assert out["wind_mw"].max() == 300.0
    assert out["solar_mw"].max() == 5.0
