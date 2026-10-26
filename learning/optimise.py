# The module description (a docstring can't hold comments, so this one covers all its lines).
"""Exact battery optimiser (linear programme per day) and the simple timer strategy.

Everything is per kWh of battery capacity. The site is assumed to use at least as much power as the
battery delivers at any moment (no export), so stored power always displaces power bought at that
half-hour's price, and results scale in a straight line with battery size.
"""
# Allows modern type-hint syntax everywhere in this file.
from __future__ import annotations

# The standard way to print progress and warning messages.
import logging
# dataclass writes the boring set-up code for a class that just holds values.
from dataclasses import dataclass
# lru_cache remembers a function's answer, so asking again with the same inputs is instant.
from functools import lru_cache

# numpy does fast maths on whole arrays of numbers at once.
import numpy as np
# SciPy's solvers: linprog for linear programmes, milp when some answers must be whole numbers (on/off).
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
# Sparse matrices store only the non-zero cells, which suits constraint tables that are mostly zeros.
from scipy.sparse import csr_matrix, lil_matrix

# Our battery settings (wear cost, timer windows and so on).
from pipeline.battery import settings

# Create a logger named after this module, so log lines show where they came from.
log = logging.getLogger(__name__)

# Each settlement period is half an hour, so power (kW) x DT gives energy (kWh).
DT = 0.5  # hours per settlement period
# Anything smaller than this counts as zero (solvers leave tiny leftovers like 0.000000000001).
TOL = 1e-7


# Marks the class below as a simple holder of values.
@dataclass
# One day's plan for the battery.
class Schedule:
    # The docstring.
    """Charge and use power (kW per kWh of capacity) and the charge level after each half-hour."""

    # Charging power in each half-hour.
    charge: np.ndarray
    # Power taken out ("use it") in each half-hour.
    use: np.ndarray
    # How full the battery is at the end of each half-hour (0 = empty, 1 = full).
    level: np.ndarray


# Remember the answer for up to 64 different combinations of inputs.
@lru_cache(maxsize=64)
# Builds the rules (constraints) the plan must obey; they depend only on the day length and battery type.
def _equalities(n: int, hours: int, efficiency: int) -> tuple[csr_matrix, np.ndarray, list[tuple[float, float]]]:
    # The docstring: lists the unknowns the solver chooses and the energy-balance rule.
    """Constraint matrix for n half-hours; cached because only the prices change from day to day.

    Variables: charge[0..n-1], use[0..n-1], level[0..n] (level[0] = start of day).
    level[t+1] = level[t] + eta*dt*charge[t] - dt/eta*use[t], and level[n] = level[0] (the day ends where it began).
    """
    # One-way efficiency: the square root of round-trip, so the loss is split between going in and coming out.
    eta = (efficiency / 100.0) ** 0.5  # split the round-trip loss evenly between charging and using
    # Most power per kWh of capacity: a 2-hour battery can move half its capacity each hour.
    power = 1.0 / hours
    # An empty table: one row per rule (n balance rules + 1 end-of-day rule), one column per unknown.
    a = lil_matrix((n + 1, 3 * n + 1))
    # For each half-hour, fill in the rule "new level = old level + charged in - taken out".
    for t in range(n):
        # The level after this half-hour...
        a[t, 2 * n + t + 1] = 1.0
        # ...minus the level before it...
        a[t, 2 * n + t] = -1.0
        # ...minus the energy charged in (after charging losses)...
        a[t, t] = -eta * DT
        # ...plus the energy taken out (more leaves the battery than arrives, because of losses)...
        a[t, n + t] = DT / eta
    # The last rule: the level at the end of the day...
    a[n, 3 * n] = 1.0
    # ...must equal the level at the start, so no day borrows energy from the next.
    a[n, 2 * n] = -1.0
    # Limits: charge and use between 0 and full power; level between empty (0) and full (1).
    bounds = [(0.0, power)] * (2 * n) + [(0.0, 1.0)] * (n + 1)
    # Return the table in a fast format, the right-hand side of every rule (all zero) and the limits.
    return a.tocsr(), np.zeros(n + 1), bounds


# Finds the cheapest possible plan for one day, given that day's prices.
def best_schedule(price: np.ndarray, hours: int, efficiency: int,
                  # A small cost for each kWh used, standing in for battery wear (stops it cycling for tiny gains).
                  wear: float = settings.WEAR_PENCE_PER_KWH / 100.0) -> Schedule:
    # The docstring.
    """The cheapest schedule for one day's prices (£/kWh), with a small wear cost per kWh used."""
    # How many half-hours in this day (48 usually; 46 or 50 when the clocks change).
    n = len(price)
    # Fetch the rules for a day this long (instant after the first time, thanks to the cache).
    a_eq, b_eq, bounds = _equalities(n, hours, efficiency)
    # What each unknown costs: charging costs the price, using saves the price (minus wear), the level is free.
    cost = np.concatenate([price * DT, (-price + wear) * DT, np.zeros(n + 1)])
    # Ask the HiGHS solver for the plan with the lowest total cost that obeys every rule.
    res = linprog(cost, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    # Status 0 means "found the best answer"; anything else is a real problem, so stop loudly.
    if res.status != 0:
        # Raise an error with the solver's own explanation.
        raise RuntimeError(f"optimiser failed: {res.message}")
    # The solver's answer: all the unknowns in one long list.
    x = res.x
    # Split it back into charging power and use power.
    charge, use = x[:n], x[n:2 * n]
    # At deeply negative prices the cheapest plan can be to charge and use at once, burning power through
    # the losses to get paid for it. A real controller doesn't do that, so re-solve with on/off switches.
    # If any half-hour both charges and uses at the same time...
    if np.any(np.minimum(charge, use) > 1e-6):
        # ...solve again with a rule that forbids it.
        x = _mixed_integer(cost, a_eq, b_eq, n, hours)
        # Split the new answer the same way.
        charge, use = x[:n], x[n:2 * n]
    # Return the plan, with solver noise rounded away and the level kept between empty and full.
    return Schedule(_clean(charge), _clean(use), np.clip(x[2 * n + 1:3 * n + 1], 0.0, 1.0))


# The same problem, but each half-hour must be either "may charge" or "may use", never both.
def _mixed_integer(cost: np.ndarray, a_eq: csr_matrix, b_eq: np.ndarray, n: int, hours: int) -> np.ndarray:
    # The docstring.
    """Same problem plus one on/off switch per half-hour: charge only when on, use only when off."""
    # Most power per kWh of capacity, as before.
    power = 1.0 / hours
    # The costs again, plus a zero cost for each new on/off switch.
    full_cost = np.concatenate([cost, np.zeros(n)])
    # A bigger rules table: the old rules plus two new rules per half-hour, and n extra columns for the switches.
    a = lil_matrix((n + 1 + 2 * n, 4 * n + 1))
    # Copy the old energy-balance rules into the top-left corner.
    a[: n + 1, : 3 * n + 1] = a_eq
    # Add the two switch rules for every half-hour.
    for t in range(n):
        # Rule 1: charging power...
        a[n + 1 + t, t] = 1.0                  # charge - power * on <= 0
        # ...can only be above zero when the switch is on.
        a[n + 1 + t, 3 * n + 1 + t] = -power
        # Rule 2: use power...
        a[n + 1 + n + t, n + t] = 1.0          # use + power * on <= power
        # ...can only be above zero when the switch is off.
        a[n + 1 + n + t, 3 * n + 1 + t] = power
    # Lower limits of each rule: the balance rules are exact; the switch rules have no lower limit.
    lo = np.concatenate([b_eq, np.full(2 * n, -np.inf)])
    # Upper limits: balance rules exact; rule 1 at most 0; rule 2 at most full power.
    hi = np.concatenate([b_eq, np.zeros(n), np.full(n, power)])
    # Every unknown is at least zero.
    lb = np.zeros(4 * n + 1)
    # Upper limits of the unknowns: full power for charge and use, 1 for the level and for each switch.
    ub = np.concatenate([np.full(2 * n, power), np.ones(n + 1), np.ones(n)])
    # Which unknowns must be whole numbers: only the switches (so each is exactly 0 or 1).
    integrality = np.concatenate([np.zeros(3 * n + 1), np.ones(n)])
    # Solve the mixed-integer problem.
    res = milp(full_cost, constraints=LinearConstraint(a.tocsr(), lo, hi),
               # Pass the limits and which unknowns are whole numbers.
               bounds=Bounds(lb, ub), integrality=integrality)
    # If the solver didn't find the best answer, stop loudly.
    if res.status != 0:
        # Raise an error with the solver's explanation.
        raise RuntimeError(f"mixed-integer optimiser failed: {res.message}")
    # Return the charge, use and level parts (the switches were only a means to an end).
    return res.x[: 3 * n + 1]


# The "simple timer" strategy: fixed times, ignoring prices.
def timer_schedule(local_hour: np.ndarray, hours: int, efficiency: int) -> Schedule:
    # The docstring.
    """Charge 01:00-05:00 and use 16:00-19:00, every day, whatever the prices.

    It stores only what it can use in the evening window, so it ends the day empty like it started.
    """
    # One-way efficiency, as in the optimiser.
    eta = (efficiency / 100.0) ** 0.5
    # Most power per kWh of capacity.
    power = 1.0 / hours
    # How many hours the evening "use it" window lasts (3).
    use_window_h = settings.TIMER_USE_HOURS[1] - settings.TIMER_USE_HOURS[0]
    # How full to charge: enough to run flat out through the evening window, but never more than full.
    target = min(1.0, power * use_window_h / eta)
    # How many half-hours in this day.
    n = len(local_hour)
    # Start with zero charging, zero use and an empty battery in every half-hour.
    charge, use, level = np.zeros(n), np.zeros(n), np.zeros(n)
    # s is the current charge level, starting empty.
    s = 0.0
    # Step through the day one half-hour at a time.
    for t, h in enumerate(local_hour):
        # If it's inside the night charging window and the battery isn't at its target yet...
        if settings.TIMER_CHARGE_HOURS[0] <= h < settings.TIMER_CHARGE_HOURS[1] and s < target:
            # ...charge at full power, or less if that would overshoot the target...
            charge[t] = min(power, (target - s) / (eta * DT))
            # ...and add the stored energy (after losses) to the level.
            s += eta * DT * charge[t]
        # Otherwise, if it's inside the evening window and there's energy stored...
        elif settings.TIMER_USE_HOURS[0] <= h < settings.TIMER_USE_HOURS[1] and s > 0:
            # ...use it at full power, or less if the battery is nearly empty...
            use[t] = min(power, s * eta / DT)
            # ...and take the energy (including losses) off the level.
            s -= DT / eta * use[t]
        # Record how full the battery is at the end of this half-hour.
        level[t] = s
    # Return the plan, with the level kept between empty and full.
    return Schedule(charge, use, np.clip(level, 0.0, 1.0))


# Works out what a plan actually earned at the real prices.
def settle(schedule: Schedule, price: np.ndarray, carbon: np.ndarray) -> dict[str, float]:
    # The docstring.
    """Money and carbon for a schedule at the prices actually paid (all per kWh of capacity)."""
    # What the charging cost: power x price x half an hour, added up over the day.
    charge_cost = float(np.sum(schedule.charge * price) * DT)
    # What using the stored power saved: the power it replaced, at that half-hour's price.
    use_value = float(np.sum(schedule.use * price) * DT)
    # Extra grid CO2 in kg: charging adds that half-hour's carbon, using removes it (nansum skips gaps).
    carbon_kg = float(np.nansum((schedule.charge - schedule.use) * carbon) * DT / 1000.0)
    # Return the results as named values.
    return {
        # The saving: what using saved minus what charging cost.
        "SavingPerKWh": use_value - charge_cost,
        # The cost of charging.
        "ChargeCostPerKWh": charge_cost,
        # The value of the power used.
        "UseValuePerKWh": use_value,
        # Full cycles: the total energy taken out, in battery-fulls.
        "CyclesPerKWh": float(np.sum(schedule.use) * DT),
        # The extra (or avoided, if negative) grid CO2.
        "CarbonKgPerKWh": carbon_kg,
    }


# Tidies the solver's numbers.
def _clean(x: np.ndarray) -> np.ndarray:
    # The docstring.
    """Round solver noise (1e-12 and the like) to exactly zero."""
    # Anything tinier than TOL, positive or negative, becomes exactly zero.
    x = np.where(np.abs(x) < TOL, 0.0, x)
    # And nothing is allowed below zero.
    return np.maximum(x, 0.0)
