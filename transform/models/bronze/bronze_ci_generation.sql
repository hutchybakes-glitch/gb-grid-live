-- One row per (record, fuel) in every raw national generation-mix file.
with raw as (
    select filename, unnest(data) as d
    from read_json(
        {{ raw_glob('ci_generation') }},
        columns = {data: 'STRUCT("from" VARCHAR, "to" VARCHAR, generationmix STRUCT(fuel VARCHAR, perc DOUBLE)[])[]'},
        filename = true
    )
),
fuels as (
    select filename, d."from" as f, d."to" as t, unnest(d.generationmix) as g
    from raw
)
select
    {{ ci_ts('f') }} as period_start_utc,
    {{ ci_ts('t') }} as period_end_utc,
    g.fuel as fuel,
    g.perc as perc,
    filename as _source_file,
    now() as _loaded_at
from fuels
