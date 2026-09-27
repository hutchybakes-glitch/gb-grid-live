-- NESO Historic Demand Data, one row per CSV row (all years). Kept as text
-- except the fields we use; date formats differ by year, so parse all three.
select
    SETTLEMENT_DATE as settlement_date_raw,
    coalesce(
        try_strptime(SETTLEMENT_DATE, '%Y-%m-%d'),
        try_strptime(SETTLEMENT_DATE, '%d-%b-%y'),
        try_strptime(SETTLEMENT_DATE, '%d-%b-%Y')
    )::date as settlement_date,
    try_cast(SETTLEMENT_PERIOD as integer) as settlement_period,
    try_cast(ND as integer) as national_demand_mw,
    try_cast(TSD as integer) as transmission_demand_mw,
    try_cast(EMBEDDED_SOLAR_GENERATION as integer) as embedded_solar_mw,
    try_cast(EMBEDDED_SOLAR_CAPACITY as integer) as embedded_solar_capacity_mw,
    -- Only present in the current-year file; older files are all actuals.
    coalesce(FORECAST_ACTUAL_INDICATOR, 'A') as forecast_actual,
    filename as _source_file,
    now() as _loaded_at
from read_csv(
    '{{ env_var("GBGL_RAW_DIR", "../data/raw") | replace("\\", "/") }}/neso_demand/*/demanddata_*.csv',
    header = true,
    all_varchar = true,
    union_by_name = true,
    filename = true
)
