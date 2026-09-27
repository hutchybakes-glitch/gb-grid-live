-- One row per national half-hour. Chunks overlap by one period and a period can
-- appear in several files; keep the version that has an actual, then the newest file.
with ranked as (
    select
        *,
        row_number() over (
            partition by period_start_utc
            order by (actual_gco2_kwh is not null) desc, _source_file desc
        ) as rn
    from {{ ref('bronze_ci_national') }}
    where period_start_utc >= timestamp '{{ var("start_date") }}'
)
select
    period_start_utc,
    period_end_utc,
    forecast_gco2_kwh,
    -- Null for recent periods: never treat as zero.
    actual_gco2_kwh,
    intensity_index,
    _source_file
from ranked
where rn = 1
