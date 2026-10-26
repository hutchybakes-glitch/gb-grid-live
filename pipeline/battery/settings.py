"""Settings for the battery pipeline: sources, date ranges, battery types and the tariff regions."""
from __future__ import annotations

from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline import config

UK = ZoneInfo("Europe/London")

# Local working folder; in Actions the powerbi-data branch is checked out here so the
# previous run's files are this run's starting state.
OUT_DIR: Path = config.REPO_ROOT / "data" / "battery"
STATE_DIR: Path = OUT_DIR / "state"

ELEXON_BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
OCTOPUS_BASE_URL = "https://api.octopus.energy/v1"
AGILE_PRODUCT = "AGILE-24-10-01"

# Prices and forecasts from here (the forecast needs a year of training data before the
# backtest starts); battery results are shown from RESULTS_START.
HISTORY_START = date(2024, 1, 1)
BACKTEST_START = date(2025, 1, 1)
RESULTS_START = date(2025, 1, 1)

# Elexon refuses longer windows on these routes (HTTP 400).
MARKET_INDEX_MAX_DAYS = 7
DGWS_CHUNK_DAYS = 7
CARBON_CHUNK_DAYS = 13

# What the planner is allowed to know: the forecast for day D is made at 17:15 UTC on D-1,
# just after Elexon publishes the day-ahead wind and solar forecast (16:45 UTC).
DECISION_TIME_UTC = time(17, 15)

# Recent days are refetched every run because late corrections still arrive.
REFETCH_RECENT_DAYS = 2

# Battery types: hours to fill at full power, and round-trip efficiency in percent.
HOURS_OPTIONS = (1, 2, 4)
EFFICIENCY_OPTIONS = (85, 90, 95)
# Wear cost per kWh delivered, so the optimiser doesn't cycle for tiny price gaps (stated on the report).
WEAR_PENCE_PER_KWH = 1.0

# The simple timer every installer sets up: charge overnight, use it in the evening peak.
TIMER_CHARGE_HOURS = (1, 5)   # 01:00-05:00 UK time
TIMER_USE_HOURS = (16, 19)    # 16:00-19:00 UK time

# Tariff estimate: VAT, the cap, and the evening peak when the extra charge applies.
VAT = 1.05
TARIFF_CAP_PENCE = 100.0
PEAK_HOURS = (16, 19)
TARIFF_FIT_DAYS = 28

# GSP group letters (the same letters dynamic tariffs use) and plain-English names.
# "W" is the wholesale view: no multiplier, no peak charge, no VAT.
REGIONS: dict[str, str] = {
    "A": "East of England",
    "B": "East Midlands",
    "C": "London",
    "D": "Merseyside and North Wales",
    "E": "West Midlands",
    "F": "North East England",
    "G": "North West England",
    "H": "Southern England",
    "J": "South East England",
    "K": "South Wales",
    "L": "South West England",
    "M": "Yorkshire",
    "N": "South Scotland",
    "P": "North Scotland",
}
WHOLESALE_CODE = "W"

# Tile-map position (column, row) and short label for each region, the same layout as the website's map.
TILES: dict[str, tuple[int, int, str]] = {
    "P": (1, 0, "N Scot"), "N": (1, 1, "S Scot"), "G": (1, 2, "NW Eng"), "F": (2, 2, "NE Eng"),
    "D": (0, 3, "N Wales"), "M": (2, 3, "Yorks"), "K": (0, 4, "S Wales"), "E": (1, 4, "W Mids"),
    "B": (2, 4, "E Mids"), "A": (3, 4, "East"), "L": (0, 5, "SW Eng"), "H": (1, 5, "South"),
    "C": (2, 5, "London"), "J": (3, 5, "SE Eng"),
}
