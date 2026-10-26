"""Exact battery optimiser (linear programme per day) and the simple timer strategy.

Everything is per kWh of battery capacity. The site is assumed to use at least as much power as the
battery delivers at any moment (no export), so stored power always displaces power bought at that
half-hour's price, and results scale in a straight line with battery size.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import csr_matrix, lil_matrix

from pipeline.battery import settings

log = logging.getLogger(__name__)

DT = 0.5  # hours per settlement period
TOL = 1e-7


@dataclass
class Schedule:
    """Charge and use power (kW per kWh of capacity) and the charge level after each half-hour."""

    charge: np.ndarray
    use: np.ndarray
    level: np.ndarray


@lru_cache(maxsize=64)
def _equalities(n: int, hours: int, efficiency: int) -> tuple[csr_matrix, np.ndarray, list[tuple[float, float]]]:
    """Constraint matrix for n half-hours; cached because only the prices change from day to day.

    Variables: charge[0..n-1], use[0..n-1], level[0..n] (level[0] = start of day).
    level[t+1] = level[t] + eta*dt*charge[t] - dt/eta*use[t], and level[n] = level[0] (the day ends where it began).
    """
    eta = (efficiency / 100.0) ** 0.5  # split the round-trip loss evenly between charging and using
    power = 1.0 / hours
    a = lil_matrix((n + 1, 3 * n + 1))
    for t in range(n):
        a[t, 2 * n + t + 1] = 1.0
        a[t, 2 * n + t] = -1.0
        a[t, t] = -eta * DT
        a[t, n + t] = DT / eta
    a[n, 3 * n] = 1.0
    a[n, 2 * n] = -1.0
    bounds = [(0.0, power)] * (2 * n) + [(0.0, 1.0)] * (n + 1)
    return a.tocsr(), np.zeros(n + 1), bounds


def best_schedule(price: np.ndarray, hours: int, efficiency: int,
                  wear: float = settings.WEAR_PENCE_PER_KWH / 100.0) -> Schedule:
    """The cheapest schedule for one day's prices (£/kWh), with a small wear cost per kWh used."""
    n = len(price)
    a_eq, b_eq, bounds = _equalities(n, hours, efficiency)
    cost = np.concatenate([price * DT, (-price + wear) * DT, np.zeros(n + 1)])
    res = linprog(cost, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if res.status != 0:
        raise RuntimeError(f"optimiser failed: {res.message}")
    x = res.x
    charge, use = x[:n], x[n:2 * n]
    # At deeply negative prices the cheapest plan can be to charge and use at once, burning power through
    # the losses to get paid for it. A real controller doesn't do that, so re-solve with on/off switches.
    if np.any(np.minimum(charge, use) > 1e-6):
        x = _mixed_integer(cost, a_eq, b_eq, n, hours)
        charge, use = x[:n], x[n:2 * n]
    return Schedule(_clean(charge), _clean(use), np.clip(x[2 * n + 1:3 * n + 1], 0.0, 1.0))


def _mixed_integer(cost: np.ndarray, a_eq: csr_matrix, b_eq: np.ndarray, n: int, hours: int) -> np.ndarray:
    """Same problem plus one on/off switch per half-hour: charge only when on, use only when off."""
    power = 1.0 / hours
    full_cost = np.concatenate([cost, np.zeros(n)])
    a = lil_matrix((n + 1 + 2 * n, 4 * n + 1))
    a[: n + 1, : 3 * n + 1] = a_eq
    for t in range(n):
        a[n + 1 + t, t] = 1.0                  # charge - power * on <= 0
        a[n + 1 + t, 3 * n + 1 + t] = -power
        a[n + 1 + n + t, n + t] = 1.0          # use + power * on <= power
        a[n + 1 + n + t, 3 * n + 1 + t] = power
    lo = np.concatenate([b_eq, np.full(2 * n, -np.inf)])
    hi = np.concatenate([b_eq, np.zeros(n), np.full(n, power)])
    lb = np.zeros(4 * n + 1)
    ub = np.concatenate([np.full(2 * n, power), np.ones(n + 1), np.ones(n)])
    integrality = np.concatenate([np.zeros(3 * n + 1), np.ones(n)])
    res = milp(full_cost, constraints=LinearConstraint(a.tocsr(), lo, hi),
               bounds=Bounds(lb, ub), integrality=integrality)
    if res.status != 0:
        raise RuntimeError(f"mixed-integer optimiser failed: {res.message}")
    return res.x[: 3 * n + 1]


def timer_schedule(local_hour: np.ndarray, hours: int, efficiency: int) -> Schedule:
    """Charge 01:00-05:00 and use 16:00-19:00, every day, whatever the prices.

    It stores only what it can use in the evening window, so it ends the day empty like it started.
    """
    eta = (efficiency / 100.0) ** 0.5
    power = 1.0 / hours
    use_window_h = settings.TIMER_USE_HOURS[1] - settings.TIMER_USE_HOURS[0]
    target = min(1.0, power * use_window_h / eta)
    n = len(local_hour)
    charge, use, level = np.zeros(n), np.zeros(n), np.zeros(n)
    s = 0.0
    for t, h in enumerate(local_hour):
        if settings.TIMER_CHARGE_HOURS[0] <= h < settings.TIMER_CHARGE_HOURS[1] and s < target:
            charge[t] = min(power, (target - s) / (eta * DT))
            s += eta * DT * charge[t]
        elif settings.TIMER_USE_HOURS[0] <= h < settings.TIMER_USE_HOURS[1] and s > 0:
            use[t] = min(power, s * eta / DT)
            s -= DT / eta * use[t]
        level[t] = s
    return Schedule(charge, use, np.clip(level, 0.0, 1.0))


def settle(schedule: Schedule, price: np.ndarray, carbon: np.ndarray) -> dict[str, float]:
    """Money and carbon for a schedule at the prices actually paid (all per kWh of capacity)."""
    charge_cost = float(np.sum(schedule.charge * price) * DT)
    use_value = float(np.sum(schedule.use * price) * DT)
    carbon_kg = float(np.nansum((schedule.charge - schedule.use) * carbon) * DT / 1000.0)
    return {
        "SavingPerKWh": use_value - charge_cost,
        "ChargeCostPerKWh": charge_cost,
        "UseValuePerKWh": use_value,
        "CyclesPerKWh": float(np.sum(schedule.use) * DT),
        "CarbonKgPerKWh": carbon_kg,
    }


def _clean(x: np.ndarray) -> np.ndarray:
    """Round solver noise (1e-12 and the like) to exactly zero."""
    x = np.where(np.abs(x) < TOL, 0.0, x)
    return np.maximum(x, 0.0)
