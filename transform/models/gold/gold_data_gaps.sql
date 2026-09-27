-- Every expected half-hour that is missing, per source and area. Expected means:
-- from the start date up to the latest period that source has delivered.
with spine as (
    select period_start_utc from {{ ref('dim_time') }}
),
observed as (
    select 'ci_national' as source, 'national' as area_id, period_start_utc
    from {{ ref('silver_ci_national') }}
    union all
    select distinct 'ci_generation', 'national', period_start_utc
    from {{ ref('silver_generation_mix') }}
    union all
    select 'ci_regional', cast(region_id as varchar), period_start_utc
    from {{ ref('silver_ci_regional') }}
    union all
    select 'pvlive', area_id, period_start_utc
    from {{ ref('silver_pvlive') }}
),
areas as (
    select source, area_id, max(period_start_utc) as last_period
    from observed
    group by all
),
expected as (
    select a.source, a.area_id, s.period_start_utc
    from areas a
    join spine s on s.period_start_utc <= a.last_period
)
select e.source, e.area_id, e.period_start_utc, cast(e.period_start_utc as date) as utc_date
from expected e
anti join observed o
    on o.source = e.source and o.area_id = e.area_id and o.period_start_utc = e.period_start_utc
