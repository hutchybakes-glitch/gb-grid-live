-- Regions ranked cleanest to dirtiest by average forecast intensity over the
-- last 30 and 365 days (ending at the latest regional period).
with latest as (
    select max(period_start_utc) as t from {{ ref('silver_ci_regional') }}
),
windows(window_days) as (values (30), (365)),
agg as (
    select
        w.window_days,
        r.region_id,
        count(*) as n,
        avg(r.forecast_gco2_kwh) as avg_gco2_kwh,
        avg(case when r.intensity_index in ('very low', 'low') then 1.0 else 0.0 end) as share_low
    from {{ ref('silver_ci_regional') }} r
    cross join windows w
    cross join latest l
    where r.region_id between 1 and 14
      and r.period_start_utc > l.t - to_days(w.window_days)
    group by all
)
select
    a.window_days,
    rank() over (partition by a.window_days order by a.avg_gco2_kwh) as rank,
    a.region_id,
    d.short_name,
    a.n,
    round(a.avg_gco2_kwh, 1) as avg_gco2_kwh,
    round(100 * a.share_low, 1) as pct_low_or_very_low
from agg a
join {{ ref('dim_region') }} d using (region_id)
