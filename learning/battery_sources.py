# The module description (a docstring can't hold comments, so this one covers all its lines).
"""Fetchers for the battery pipeline. Each returns a tidy DataFrame keyed by half-hour start in UTC.

Elexon (wholesale prices, day-ahead wind/solar and demand forecasts) and the Carbon Intensity API are
openly licensed and published. Octopus Agile prices are fetched only to calibrate the tariff formula;
its terms don't allow republishing them, so they never leave this process.
"""
# Allows modern type-hint syntax everywhere in this file.
from __future__ import annotations

# The standard way to print progress messages.
import logging
# Days, moments in time, lengths of time, and the UTC time zone.
from datetime import date, datetime, timedelta, timezone

# pandas holds tables of data.
import pandas as pd

# The project's general settings (imported so other modules can reach it through this one).
from pipeline import config
# The battery settings: base URLs, chunk sizes, the decision time, the UK time zone.
from pipeline.battery import settings
# Our polite web client (rate limiting and retries; see learning/http.py).
from pipeline.http import ApiClient

# Create a logger named after this module, so log lines show where they came from.
log = logging.getLogger(__name__)


# Turns a moment in time into the text format the APIs want.
def _iso(ts: datetime) -> str:
    # The docstring.
    """Format a UTC datetime the way Elexon and Octopus expect (minute precision, Z suffix)."""
    # Convert to UTC and write it like 2026-10-26T17:15Z.
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


# Finds when a UK day starts and ends in UTC.
def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    # The docstring.
    """UTC start and end of a UK local day (23, 24 or 25 hours long)."""
    # UK midnight at the start of the day, converted to UTC (23:00 the day before in summer).
    start = datetime.combine(day, datetime.min.time(), settings.UK).astimezone(timezone.utc)
    # UK midnight at the start of the next day, converted to UTC.
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), settings.UK).astimezone(timezone.utc)
    # Return both; on clock-change days they're 23 or 25 hours apart.
    return start, end


# The "no peeking" rule in one place.
def decision_cutoff(day: date) -> datetime:
    # The docstring.
    """The latest moment information may be used to plan ``day``: 17:15 UTC the day before."""
    # The day before, at the decision time (17:15 UTC).
    return datetime.combine(day - timedelta(days=1), settings.DECISION_TIME_UTC, timezone.utc)


# Downloads the actual wholesale prices.
def market_index(client: ApiClient, first: date, last: date) -> pd.DataFrame:
    # The docstring.
    """Actual wholesale price (APX market index, £/MWh) for UK local days ``first``..``last``."""
    # The UTC start of the first day.
    start, _ = local_day_bounds(first)
    # The UTC end of the last day.
    _, end = local_day_bounds(last)
    # The pieces downloaded so far.
    frames = []
    # a = the start of the current piece.
    a = start
    # Keep going until the whole range is covered.
    while a < end:
        # The route rejects windows over 7 days, and treats ``to`` as inclusive.
        # The end of this piece: 7 days on, or the end of the range if that's sooner.
        b = min(a + timedelta(days=settings.MARKET_INDEX_MAX_DAYS), end)
        # Ask Elexon for this piece.
        body = client.get_json(
            # The route for market index prices.
            "balancing/pricing/market-index",
            # From a to one minute before b (so the end isn't counted twice), as JSON.
            {"from": _iso(a), "to": _iso(b - timedelta(minutes=1)), "format": "json"},
        )
        # Keep only the APX provider's rows (the other provider's rows are all zero).
        rows = [r for r in body["data"] if r["dataProvider"] == "APXMIDP"]
        # If anything came back...
        if rows:
            # ...turn it into a table and keep it.
            frames.append(pd.DataFrame({
                # The half-hour's start time in UTC.
                "period_start_utc": pd.to_datetime([r["startTime"] for r in rows], utc=True),
                # The price in £/MWh.
                "price": [float(r["price"]) for r in rows],
                # Zero volume means no trades: the 0 price is a placeholder, not a real price.
                # The traded volume, used below to drop those placeholders.
                "volume": [float(r["volume"]) for r in rows],
            }))
        # Move on to the next piece.
        a = b
    # If nothing came back at all...
    if not frames:
        # ...return an empty table with the right columns.
        return pd.DataFrame(columns=["period_start_utc", "price"])
    # Join the pieces, keeping one row per half-hour (the latest if repeated).
    df = pd.concat(frames).drop_duplicates("period_start_utc", keep="last")
    # Drop half-hours with no trades.
    df = df[df["volume"] > 0]
    # Return the time and price, in time order, numbered from 0.
    return df[["period_start_utc", "price"]].sort_values("period_start_utc").reset_index(drop=True)


# Downloads Elexon's day-ahead wind and solar forecasts.
def wind_solar_forecast(client: ApiClient, first: date, last: date) -> pd.DataFrame:
    # The docstring.
    """Day-ahead wind and solar forecast (MW) as known at each day's decision time."""
    # The pieces downloaded so far.
    frames = []
    # The route groups by UTC day, so in BST the first hour of a UK day sits in the previous UTC day.
    # So start one day early.
    d = first - timedelta(days=1)
    # Work through the days in chunks.
    while d <= last:
        # The last day of this chunk.
        e = min(d + timedelta(days=settings.DGWS_CHUNK_DAYS - 1), last)
        # Ask Elexon for this chunk.
        body = client.get_json(
            # The day-ahead wind and solar forecast route.
            "forecast/generation/wind-and-solar/day-ahead",
            # ``to`` must be after ``from`` or only one period comes back; extra rows are trimmed below.
            # From the first day to the day after the last, day-ahead forecasts only, as JSON.
            {"from": d.isoformat(), "to": (e + timedelta(days=1)).isoformat(),
             # (continued) the forecast type and the format.
             "processType": "day ahead", "format": "json"},
        )
        # If anything came back, keep it.
        if body["data"]:
            # Add this chunk's rows to the list.
            frames.append(pd.DataFrame(body["data"]))
        # Move on to the day after this chunk.
        d = e + timedelta(days=1)
    # If nothing came back at all...
    if not frames:
        # ...return an empty table with the right columns.
        return pd.DataFrame(columns=["period_start_utc", "wind_mw", "solar_mw"])
    # Join the chunks into one table.
    raw = pd.concat(frames)
    # Read each half-hour's start time as a UTC time.
    raw["period_start_utc"] = pd.to_datetime(raw["startTime"], utc=True)
    # Read when each forecast was published.
    raw["publish_utc"] = pd.to_datetime(raw["publishTime"], utc=True)
    # Each request also returns the first half-hour of the next chunk, so the same row arrives twice at chunk
    # boundaries; without this the wind and solar for those half-hours were summed twice (found in review).
    # Drop exact repeats (same half-hour, same type, same publication).
    raw = raw.drop_duplicates(["period_start_utc", "psrType", "publish_utc"])
    # Keep only the forecast that was available at the decision time.
    raw = _keep_known_at_decision(raw)
    # Sort the generation types into two columns: solar, and wind (offshore and onshore together).
    raw["kind"] = raw["psrType"].map({"Solar": "solar_mw", "Wind Offshore": "wind_mw", "Wind Onshore": "wind_mw"})
    # Add up each half-hour's MW per column and turn the table so each type is a column.
    wide = raw.groupby(["period_start_utc", "kind"])["quantity"].sum().unstack("kind").reset_index()
    # Keep only the requested UK days.
    return _trim_to_days(wide, first, last)


# Downloads Elexon's day-ahead national demand forecast.
def demand_forecast(client: ApiClient, first: date, last: date) -> pd.DataFrame:
    # The docstring.
    """Day-ahead national demand forecast (MW) as known at each day's decision time."""
    # The pieces downloaded so far.
    frames = []
    # Start at the first day.
    d = first
    # One request per day.
    while d <= last:
        # The decision time for this day (17:15 UTC the day before).
        cutoff = decision_cutoff(d)
        # Publications are listed by publish time, at most one day per call: ask for the day before up to the cutoff.
        # Ask Elexon for every forecast published that day up to the cutoff.
        body = client.get_json(
            # The national demand forecast dataset.
            "datasets/NDF",
            # From midnight on the day before...
            {"publishDateTimeFrom": _iso(cutoff.replace(hour=0, minute=0)),
             # ...to the cutoff, as JSON.
             "publishDateTimeTo": _iso(cutoff), "format": "json"},
        )
        # If anything came back, keep it.
        if body["data"]:
            # Add this day's rows to the list.
            frames.append(pd.DataFrame(body["data"]))
        # Move on to the next day.
        d += timedelta(days=1)
    # If nothing came back at all...
    if not frames:
        # ...return an empty table with the right columns.
        return pd.DataFrame(columns=["period_start_utc", "demand_mw"])
    # Join the days into one table.
    raw = pd.concat(frames)
    # Read each half-hour's start time as a UTC time.
    raw["period_start_utc"] = pd.to_datetime(raw["startTime"], utc=True)
    # Read when each forecast was published.
    raw["publish_utc"] = pd.to_datetime(raw["publishTime"], utc=True)
    # Keep only the latest forecast available at the decision time.
    raw = _keep_known_at_decision(raw)
    # One demand figure per half-hour, with the column renamed to demand_mw.
    out = raw.groupby("period_start_utc", as_index=False)["demand"].last().rename(columns={"demand": "demand_mw"})
    # Keep only the requested UK days.
    return _trim_to_days(out, first, last)


# Downloads how much CO2 each kWh from the grid caused.
def carbon_intensity(client: ApiClient, first: date, last: date) -> pd.DataFrame:
    # The docstring.
    """National carbon intensity (gCO2/kWh): actual where published, otherwise the forecast."""
    # The pieces downloaded so far.
    frames = []
    # Start at the first day.
    d = first
    # Work through the days in chunks.
    while d <= last:
        # The last day of this chunk.
        e = min(d + timedelta(days=settings.CARBON_CHUNK_DAYS - 1), last)
        # The UTC start of the chunk's first day.
        a, _ = local_day_bounds(d)
        # The UTC end of the chunk's last day.
        _, b = local_day_bounds(e)
        # ``{from}`` returns the period *ending* at from, so start 30 minutes later to get periods starting at a.
        # Build the address (this API takes the dates in the path, not as parameters).
        path = f"https://api.carbonintensity.org.uk/intensity/{_iso(a + timedelta(minutes=30))}/{_iso(b)}"
        # Download it.
        body = client.get_json(path)
        # The rows, or an empty list if there are none.
        rows = body.get("data", [])
        # If anything came back...
        if rows:
            # ...turn it into a table and keep it.
            frames.append(pd.DataFrame({
                # The half-hour's start time in UTC.
                "period_start_utc": pd.to_datetime([r["from"] for r in rows], utc=True),
                # The actual intensity if it's been published...
                "carbon": [r["intensity"]["actual"] if r["intensity"]["actual"] is not None
                           # ...otherwise the forecast.
                           else r["intensity"]["forecast"] for r in rows],
            }))
        # Move on to the day after this chunk.
        d = e + timedelta(days=1)
    # If nothing came back at all...
    if not frames:
        # ...return an empty table with the right columns.
        return pd.DataFrame(columns=["period_start_utc", "carbon"])
    # Join the chunks, drop blanks, and keep one row per half-hour.
    out = pd.concat(frames).dropna().drop_duplicates("period_start_utc", keep="last")
    # Keep only the requested UK days.
    return _trim_to_days(out, first, last)


# Downloads a region's real dynamic tariff prices, only to fit the formula (they are never published).
def agile_prices(client: ApiClient, region: str, first: date, last: date) -> pd.DataFrame:
    # The docstring.
    """Dynamic tariff prices for one region, for calibration only (never written to the published files)."""
    # The UTC start of the first day.
    start, _ = local_day_bounds(first)
    # The UTC end of the last day.
    _, end = local_day_bounds(last)
    # The tariff's code for this region.
    tariff = f"E-1R-{settings.AGILE_PRODUCT}-{region}"
    # Download the unit rates.
    body = client.get_json(
        # The address of this tariff's unit rates.
        f"{settings.OCTOPUS_BASE_URL}/products/{settings.AGILE_PRODUCT}/electricity-tariffs/{tariff}/standard-unit-rates/",
        # Up to 1,500 rows in one page, for the requested time range.
        {"page_size": "1500", "period_from": _iso(start), "period_to": _iso(end)},
    )
    # The rows, or an empty list.
    rows = body.get("results", [])
    # Return a table of the prices.
    return pd.DataFrame({
        # The half-hour's start time in UTC.
        "period_start_utc": pd.to_datetime([r["valid_from"] for r in rows], utc=True),
        # The price before VAT, in pence per kWh.
        "exc_vat": [float(r["value_exc_vat"]) for r in rows],
        # The price including VAT.
        "inc_vat": [float(r["value_inc_vat"]) for r in rows],
    })


# The honesty filter: throws away any forecast published too late to have been used.
def _keep_known_at_decision(raw: pd.DataFrame) -> pd.DataFrame:
    # The docstring.
    """Keep, for each half-hour, only rows published before that day's decision time.

    This is what makes the backtest honest: the planner never sees a forecast it couldn't have had.
    """
    # The UK day each half-hour belongs to.
    local_day = raw["period_start_utc"].dt.tz_convert(settings.UK).dt.date
    # That day's decision cutoff, for every row.
    cutoff = local_day.map(lambda d: pd.Timestamp(decision_cutoff(d)))
    # Keep only rows published at or before the cutoff.
    known = raw[raw["publish_utc"] <= cutoff].copy()
    # Of what was known, the latest publication wins.
    # For each half-hour, the newest publish time among the known rows.
    latest = known.groupby("period_start_utc")["publish_utc"].transform("max")
    # Keep only the rows from that newest publication.
    return known[known["publish_utc"] == latest]


# Cuts a table down to whole UK days.
def _trim_to_days(df: pd.DataFrame, first: date, last: date) -> pd.DataFrame:
    # The docstring.
    """Keep only half-hours that fall in UK local days ``first``..``last``."""
    # The UTC start of the first day.
    start, _ = local_day_bounds(first)
    # The UTC end of the last day.
    _, end = local_day_bounds(last)
    # True for rows inside the range.
    mask = (df["period_start_utc"] >= start) & (df["period_start_utc"] < end)
    # Keep those rows, in time order, numbered from 0.
    return df[mask].sort_values("period_start_utc").reset_index(drop=True)


# Makes the web client used for Elexon.
def elexon_client() -> ApiClient:
    # The docstring.
    """A polite client for Elexon (one request a second, retries with backoff)."""
    # A client pointed at Elexon's base address.
    return ApiClient(settings.ELEXON_BASE_URL)


# The names other modules may import from this one.
__all__ = [
    # The fetchers...
    "market_index", "wind_solar_forecast", "demand_forecast", "carbon_intensity", "agile_prices",
    # ...and the helpers.
    "local_day_bounds", "decision_cutoff", "elexon_client", "config",
]
