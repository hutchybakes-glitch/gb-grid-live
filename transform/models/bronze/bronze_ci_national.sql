-- One row per record in every raw national intensity file (duplicates kept).
with raw as (
    select filename, unnest(data) as d
    from read_json(
        {{ raw_glob('ci_national') }},
        columns = {data: 'STRUCT("from" VARCHAR, "to" VARCHAR, intensity STRUCT(forecast INTEGER, actual INTEGER, "index" VARCHAR))[]'},
        filename = true
    )
)
select
    {{ ci_ts('d."from"') }} as period_start_utc,
    {{ ci_ts('d."to"') }} as period_end_utc,
    d.intensity.forecast as forecast_gco2_kwh,
    d.intensity.actual as actual_gco2_kwh,
    d.intensity."index" as intensity_index,
    filename as _source_file,
    now() as _loaded_at
from raw
