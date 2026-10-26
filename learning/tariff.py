# The module description (a docstring can't hold comments, so this one covers all its lines).
"""The "typical dynamic tariff" estimate: a formula on the wholesale price, fitted per region.

Octopus's terms don't allow republishing Agile prices, but their blog describes the shape of the formula:
price = multiplier x wholesale + an extra charge in the 16:00-19:00 peak, plus VAT, capped at 100p.
We fit the multiplier and peak charge per region on recent Agile prices and publish only those numbers
and the fit error. The report labels the result as an estimate, not any supplier's price.
"""
# Allows modern type-hint syntax everywhere in this file.
from __future__ import annotations

# The standard way to print warning messages.
import logging
# dataclass writes the set-up code for a class that just holds values.
from dataclasses import dataclass

# numpy does fast maths on arrays, including least-squares fitting.
import numpy as np
# pandas holds tables of data and joins them.
import pandas as pd

# Our battery settings (VAT, the price cap, the peak hours, the UK time zone).
from pipeline.battery import settings

# Create a logger named after this module, so log lines show where they came from.
log = logging.getLogger(__name__)


# Marks the class below as a simple holder of values.
@dataclass
# The result of fitting the formula for one region.
class TariffFit:
    # The docstring.
    """Fitted formula for one region, and how well it matched."""

    # The region's letter code (A to P).
    region: str
    # How many times the wholesale price the tariff charges.
    multiplier: float
    # The extra pence per kWh added in the evening peak.
    peak_charge: float
    # The average gap between the formula and the real tariff, in pence.
    error_p: float
    # How closely the formula's ups and downs follow the real tariff (1 = perfectly).
    correlation: float
    # How many days the fit used.
    days: int
    # The last day in the fit.
    fit_end: str


# Marks which half-hours are in the evening peak.
def is_peak(period_start_utc: pd.Series) -> np.ndarray:
    # The docstring.
    """1 for half-hours starting 16:00-18:30 UK local time, else 0."""
    # The UK local hour of each half-hour (so the peak follows the clocks in summer).
    hour = period_start_utc.dt.tz_convert(settings.UK).dt.hour
    # 1.0 where the hour is from 16 up to (not including) 19, otherwise 0.0.
    return ((hour >= settings.PEAK_HOURS[0]) & (hour < settings.PEAK_HOURS[1])).to_numpy(dtype=float)


# The formula itself.
def tariff_pence(wholesale_gbp_mwh: np.ndarray, peak: np.ndarray, multiplier: float, peak_charge: float) -> np.ndarray:
    # The docstring.
    """Estimated tariff in p/kWh including VAT, from the wholesale price in £/MWh (÷10 gives p/kWh)."""
    # VAT x (multiplier x wholesale in pence, plus the peak charge in peak half-hours).
    raw = settings.VAT * (multiplier * wholesale_gbp_mwh / 10.0 + peak_charge * peak)
    # Never above the tariff's cap (100p).
    return np.minimum(raw, settings.TARIFF_CAP_PENCE)


# Fits the formula for one region against recent real tariff prices.
def fit(region: str, agile: pd.DataFrame, prices: pd.DataFrame) -> TariffFit | None:
    # The docstring.
    """Least-squares fit of multiplier and peak charge (no intercept: free wholesale power off-peak costs ~0)."""
    # Line up each tariff price with the wholesale price for the same half-hour.
    df = agile.merge(prices, on="period_start_utc", how="inner")
    # With less than a week of matching half-hours, the fit wouldn't be trustworthy...
    if len(df) < 48 * 7:
        # ...so say so in the log...
        log.warning("Tariff fit for %s skipped: only %d matching half-hours", region, len(df))
        # ...and return nothing.
        return None
    # Which half-hours are in the peak.
    peak = is_peak(df["period_start_utc"])
    # The wholesale price in pence per kWh.
    w = df["price"].to_numpy() / 10.0
    # Half-hours at the cap are cut off by it, so they would bias the slope.
    # Keep only half-hours comfortably below the cap.
    ok = df["inc_vat"].to_numpy() < settings.TARIFF_CAP_PENCE - 5
    # The inputs table: wholesale price and the peak flag, for the kept half-hours.
    a = np.column_stack([w, peak])[ok]
    # Least squares: the multiplier and peak charge that best match the tariff before VAT.
    coef, *_ = np.linalg.lstsq(a, df["exc_vat"].to_numpy()[ok], rcond=None)
    # What the fitted formula predicts for every half-hour (including VAT and the cap).
    pred = tariff_pence(df["price"].to_numpy(), peak, coef[0], coef[1])
    # The real tariff prices including VAT.
    actual = df["inc_vat"].to_numpy()
    # The UK calendar day of each half-hour, to count days and find the last one.
    days = df["period_start_utc"].dt.tz_convert(settings.UK).dt.date
    # Return the fit, rounded to sensible precision.
    return TariffFit(
        # The region code.
        region=region,
        # The fitted multiplier.
        multiplier=round(float(coef[0]), 4),
        # The fitted peak charge.
        peak_charge=round(float(coef[1]), 3),
        # The average miss in pence.
        error_p=round(float(np.mean(np.abs(pred - actual))), 2),
        # How well the shape matches.
        correlation=round(float(np.corrcoef(pred, actual)[0, 1]), 4),
        # How many distinct days were used.
        days=int(days.nunique()),
        # The last day used, as text.
        fit_end=str(days.max()),
    )


# The price a battery pays and saves in one region.
def region_prices_gbp_per_kwh(wholesale_gbp_mwh: np.ndarray, peak: np.ndarray, region: str,
                              # The table of fitted formulas, one row per region.
                              fits: pd.DataFrame) -> np.ndarray:
    # The docstring.
    """Price the battery pays and saves, in £/kWh, for a region (or W = wholesale)."""
    # "W" means the plain wholesale market, with no tariff on top...
    if region == settings.WHOLESALE_CODE:
        # ...so just turn £/MWh into £/kWh.
        return wholesale_gbp_mwh / 1000.0
    # Otherwise fetch the region's fitted formula...
    row = fits.loc[region]
    # ...apply it, and turn pence into pounds.
    return tariff_pence(wholesale_gbp_mwh, peak, row["Multiplier"], row["PeakCharge"]) / 100.0
