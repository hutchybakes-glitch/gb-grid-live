-- The 48-hour regional forecast from the most recent snapshot, one row per
-- (region, half-hour). Feeds the Plan page chart and best-window finder.
with latest as (
    select max(captured_at) as captured_at
    from {{ ref('bronze_forecast_snapshots') }}
    where scope = 'regional'
)
select
    s.region_id,
    r.short_name,
    s.period_start_utc,
    s.forecast_gco2_kwh,
    s.intensity_index,
    s.captured_at
from {{ ref('bronze_forecast_snapshots') }} s
join latest l on s.captured_at = l.captured_at
join {{ ref('dim_region') }} r on r.region_id = s.region_id
where s.scope = 'regional'
  -- Drop the period that ended before capture (see DECISIONS: {from} quirk).
  and s.period_start_utc + interval 30 minute > s.captured_at
