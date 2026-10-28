# DATA.md — sources, tables and known gotchas

Both sources are free and need no API key. Verify every endpoint against the live docs before relying on it; if anything here is wrong, trust the docs and log the correction in `docs/DECISIONS.md`.

## Source 1: Carbon Intensity API (NESO)
- Base URL: `https://api.carbonintensity.org.uk` — docs: https://carbon-intensity.github.io/api-definitions/
- Licence: CC BY 4.0. All times UTC. Half-hourly.

| Endpoint | Use |
| --- | --- |
| `/intensity/{from}/{to}` | National forecast + actual + index. **Max range 14 days** per request — chunk backfills. |
| `/intensity/{from}/fw48h` | National forecast for next 48h (daily snapshot for vintages). |
| `/generation/{from}/{to}` | National generation mix (% by fuel). |
| `/regional/intensity/{from}/{to}` | All regions: forecast intensity + generation mix. Assume the same 14-day limit; confirm. |
| `/regional/intensity/{from}/fw48h` | All regions, next 48h (daily snapshot). |
| `/intensity/factors` | gCO₂/kWh factor per fuel type (reference table). |

- Regions: ids 1–14 are DNO regions (3 = North West England, "Electricity North West"); 15 England, 16 Scotland, 17 Wales, 18 GB. Build `dim_region` from an API response, don't hard-code names.
- **Regional data has forecasts only, no actuals.** Accuracy analysis is national only; say so on the site.
- Datetimes use format `YYYY-MM-DDThh:mmZ`.

## Source 2: PV_Live (Sheffield Solar, funded by NESO)
- Base URL: `https://api.pvlive.uk/pvlive/api/v4/` — guide: https://api.solar.sheffield.ac.uk/pvlive/gdocs — Python reference: https://github.com/SheffieldSolar/PV_Live-API
- `gsp/0` = national estimate; other GSP ids and PES (DNO area) ids come from the list endpoints — look them up, don't guess.
- Params: `start`, `end`, `extra_fields` (request `updated_gmt`, and capacity if available). 30-minute resolution only.
- Response: `data` is an array of tuples; take column names from `meta`, never assume order.
- **Estimates are revised.** Use (`gsp_id`, `datetime_gmt`, `updated_gmt`) as the raw key and keep the latest version in silver.
- The API is under active development — isolate it behind one client module.
- Covers Great Britain only, solar not in the Balancing Mechanism.

## Forecast vintages (important — explain this on the Trust page)
Historical `/intensity/{from}/{to}` calls return one forecast per period, which is likely the latest forecast issued, not the day-ahead one. To measure real 24h-ahead accuracy, the pipeline must **snapshot the fw48h forecasts every day** into `bronze_forecast_snapshots` with a `captured_at` timestamp. Accuracy based on snapshots starts from the day the pipeline first runs; the backfilled history is labelled "final forecast vs actual".

## Backfill
- Carbon intensity national + regional + generation: from 2023-01-01 to today, in ≤14-day chunks, politely rate-limited.
- PV_Live national (gsp/0) and the 14 DNO/PES areas: same period.
- Backfill must be resumable (skip chunks already on disk) and idempotent.

## Tables (dbt)
| Layer | Table | Grain / key |
| --- | --- | --- |
| bronze | `bronze_ci_national`, `bronze_ci_regional`, `bronze_ci_generation`, `bronze_pvlive`, `bronze_forecast_snapshots` | one row per raw record, plus `_loaded_at`, `_source_file` |
| silver | `silver_ci_national` | `period_start_utc` (unique) |
| silver | `silver_ci_regional` | `region_id`, `period_start_utc` |
| silver | `silver_generation_mix` | `period_start_utc`, `fuel` (national) and regional equivalent |
| silver | `silver_pvlive` | `area_id`, `period_start_utc` (latest revision only) |
| gold | `gold_region_now`, `gold_region_48h`, `gold_forecast_accuracy`, `gold_heatmap_hour_month`, `gold_region_league`, `gold_solar_vs_demand`, `gold_model_backtest`, `gold_pipeline_health` | shaped for one chart each |
| dim | `dim_region`, `dim_time` (half-hour slots, UK local time, clock-change flag) | |

## Data tests (minimum)
- Unique + not-null keys on every silver table.
- Intensity between 0 and 1000 gCO₂/kWh; generation percentages per period sum to 100 ± 1.
- Solar generation ≥ 0 and ≤ installed capacity.
- Completeness: each UTC day has 48 half-hours (flag gaps, don't fail the build; publish them on the data quality panel).
- Freshness: latest national period within 2 hours of run time (warn only when run offline).

## Known gotchas
- UK clock changes: local days have 46 or 50 half-hours. Work in UTC; convert only for display.
- `actual` is null for recent periods; never treat null as zero.
- Some historical periods may be missing or duplicated — deduplicate, count, and report.
