-- One row per (record, region) in every raw regional file. The generation mix
-- stays as a list here; silver unnests it, which keeps this table ~9x smaller.
with raw as (
    select filename, unnest(data) as d
    from read_json(
        {{ raw_glob('ci_regional') }},
        columns = {data: 'STRUCT("from" VARCHAR, "to" VARCHAR, regions STRUCT(regionid INTEGER, dnoregion VARCHAR, shortname VARCHAR, intensity STRUCT(forecast INTEGER, "index" VARCHAR), generationmix STRUCT(fuel VARCHAR, perc DOUBLE)[])[])[]'},
        filename = true,
        maximum_object_size = 104857600
    )
),
regions as (
    select filename, d."from" as f, d."to" as t, unnest(d.regions) as r
    from raw
)
select
    {{ ci_ts('f') }} as period_start_utc,
    {{ ci_ts('t') }} as period_end_utc,
    r.regionid as region_id,
    r.dnoregion as dno_region,
    r.shortname as short_name,
    r.intensity.forecast as forecast_gco2_kwh,
    r.intensity."index" as intensity_index,
    r.generationmix as generation_mix,
    filename as _source_file,
    now() as _loaded_at
from regions
