-- One row per (region, half-hour): forecast intensity plus its generation mix list.
-- Regional data has forecasts only; there is no regional actual.
with ranked as (
    select
        *,
        row_number() over (
            partition by region_id, period_start_utc
            order by _source_file desc
        ) as rn
    from {{ ref('bronze_ci_regional') }}
    where period_start_utc >= timestamp '{{ var("start_date") }}'
)
select
    region_id,
    period_start_utc,
    period_end_utc,
    forecast_gco2_kwh,
    intensity_index,
    generation_mix,
    _source_file
from ranked
where rn = 1
