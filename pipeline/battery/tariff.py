"""The "typical dynamic tariff" estimate: a formula on the wholesale price, fitted per region.

Octopus's terms don't allow republishing Agile prices, but their blog describes the shape of the formula:
price = multiplier x wholesale + an extra charge in the 16:00-19:00 peak, plus VAT, capped at 100p.
We fit the multiplier and peak charge per region on recent Agile prices and publish only those numbers
and the fit error. The report labels the result as an estimate, not any supplier's price.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pipeline.battery import settings

log = logging.getLogger(__name__)


@dataclass
class TariffFit:
    """Fitted formula for one region, and how well it matched."""

    region: str
    multiplier: float
    peak_charge: float
    error_p: float
    correlation: float
    days: int
    fit_end: str


def is_peak(period_start_utc: pd.Series) -> np.ndarray:
    """1 for half-hours starting 16:00-18:30 UK local time, else 0."""
    hour = period_start_utc.dt.tz_convert(settings.UK).dt.hour
    return ((hour >= settings.PEAK_HOURS[0]) & (hour < settings.PEAK_HOURS[1])).to_numpy(dtype=float)


def tariff_pence(wholesale_gbp_mwh: np.ndarray, peak: np.ndarray, multiplier: float, peak_charge: float) -> np.ndarray:
    """Estimated tariff in p/kWh including VAT, from the wholesale price in £/MWh (÷10 gives p/kWh)."""
    raw = settings.VAT * (multiplier * wholesale_gbp_mwh / 10.0 + peak_charge * peak)
    return np.minimum(raw, settings.TARIFF_CAP_PENCE)


def fit(region: str, agile: pd.DataFrame, prices: pd.DataFrame) -> TariffFit | None:
    """Least-squares fit of multiplier and peak charge (no intercept: free wholesale power off-peak costs ~0)."""
    df = agile.merge(prices, on="period_start_utc", how="inner")
    if len(df) < 48 * 7:
        log.warning("Tariff fit for %s skipped: only %d matching half-hours", region, len(df))
        return None
    peak = is_peak(df["period_start_utc"])
    w = df["price"].to_numpy() / 10.0
    # Half-hours at the cap are cut off by it, so they would bias the slope.
    ok = df["inc_vat"].to_numpy() < settings.TARIFF_CAP_PENCE - 5
    a = np.column_stack([w, peak])[ok]
    coef, *_ = np.linalg.lstsq(a, df["exc_vat"].to_numpy()[ok], rcond=None)
    pred = tariff_pence(df["price"].to_numpy(), peak, coef[0], coef[1])
    actual = df["inc_vat"].to_numpy()
    days = df["period_start_utc"].dt.tz_convert(settings.UK).dt.date
    return TariffFit(
        region=region,
        multiplier=round(float(coef[0]), 4),
        peak_charge=round(float(coef[1]), 3),
        error_p=round(float(np.mean(np.abs(pred - actual))), 2),
        correlation=round(float(np.corrcoef(pred, actual)[0, 1]), 4),
        days=int(days.nunique()),
        fit_end=str(days.max()),
    )


def region_prices_gbp_per_kwh(wholesale_gbp_mwh: np.ndarray, peak: np.ndarray, region: str,
                              fits: pd.DataFrame) -> np.ndarray:
    """Price the battery pays and saves, in £/kWh, for a region (or W = wholesale)."""
    if region == settings.WHOLESALE_CODE:
        return wholesale_gbp_mwh / 1000.0
    row = fits.loc[region]
    return tariff_pence(wholesale_gbp_mwh, peak, row["Multiplier"], row["PeakCharge"]) / 100.0
