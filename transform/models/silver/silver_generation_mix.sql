-- National generation mix: one row per (half-hour, fuel).
with ranked as (
    select
        *,
        row_number() over (
            partition by period_start_utc, fuel
            order by _source_file desc
        ) as rn
    from {{ ref('bronze_ci_generation') }}
    where period_start_utc >= timestamp '{{ var("start_date") }}'
)
select period_start_utc, fuel, perc
from ranked
where rn = 1
