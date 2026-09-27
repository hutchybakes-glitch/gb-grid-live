-- True ahead-of-time accuracy from this project's own fw48h snapshots: what the
-- forecast said at capture time vs the actual later measured. Grouped by how
-- far ahead the forecast was. Grows by one day of snapshots per daily run.
with s as (
    select
        s.captured_at,
        s.period_start_utc,
        s.forecast_gco2_kwh,
        n.actual_gco2_kwh,
        date_diff('minute', s.captured_at, s.period_start_utc) / 60.0 as lead_hours
    from {{ ref('bronze_forecast_snapshots') }} s
    join {{ ref('silver_ci_national') }} n using (period_start_utc)
    where s.scope = 'national'
      and n.actual_gco2_kwh is not null
      and s.period_start_utc >= s.captured_at
),
bucketed as (
    select *,
        case
            when lead_hours < 6 then '0-6h'
            when lead_hours < 12 then '6-12h'
            when lead_hours < 24 then '12-24h'
            when lead_hours < 36 then '24-36h'
            else '36-48h'
        end as lead_bucket
    from s
)
select
    lead_bucket,
    min(lead_hours) as min_lead_hours,
    count(*) as n,
    count(distinct cast(captured_at as date)) as snapshot_days,
    round(avg(abs(actual_gco2_kwh - forecast_gco2_kwh)), 2) as mae,
    round(avg(actual_gco2_kwh - forecast_gco2_kwh), 2) as bias
from bucketed
group by lead_bucket
