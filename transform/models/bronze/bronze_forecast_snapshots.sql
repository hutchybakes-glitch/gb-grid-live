-- Every fw48h forecast ever captured, national (region_id null) and regional.
-- Never deduplicated: each captured_at is a separate forecast vintage.
with national as (
    select filename, captured_at, unnest(data) as d
    from read_json(
        '{{ env_var("GBGL_RAW_DIR", "../data/raw") | replace("\\", "/") }}/forecast_snapshots/*/fw48h_national_*.json',
        columns = {captured_at: 'VARCHAR', data: 'STRUCT("from" VARCHAR, "to" VARCHAR, intensity STRUCT(forecast INTEGER, "index" VARCHAR))[]'},
        filename = true
    )
),
regional_periods as (
    select filename, captured_at, unnest(data) as d
    from read_json(
        '{{ env_var("GBGL_RAW_DIR", "../data/raw") | replace("\\", "/") }}/forecast_snapshots/*/fw48h_regional_*.json',
        columns = {captured_at: 'VARCHAR', data: 'STRUCT("from" VARCHAR, "to" VARCHAR, regions STRUCT(regionid INTEGER, intensity STRUCT(forecast INTEGER, "index" VARCHAR), generationmix STRUCT(fuel VARCHAR, perc DOUBLE)[])[])[]'},
        filename = true
    )
),
regional as (
    select filename, captured_at, d."from" as f, d."to" as t, unnest(d.regions) as r
    from regional_periods
)
select
    strptime(captured_at, '%Y-%m-%dT%H:%M:%SZ') as captured_at,
    'national' as scope,
    cast(null as integer) as region_id,
    {{ ci_ts('d."from"') }} as period_start_utc,
    d.intensity.forecast as forecast_gco2_kwh,
    d.intensity."index" as intensity_index,
    cast(null as STRUCT(fuel VARCHAR, perc DOUBLE)[]) as generation_mix,
    filename as _source_file,
    now() as _loaded_at
from national
union all
select
    strptime(captured_at, '%Y-%m-%dT%H:%M:%SZ'),
    'regional',
    r.regionid,
    {{ ci_ts('f') }},
    r.intensity.forecast,
    r.intensity."index",
    r.generationmix,
    filename,
    now()
from regional
