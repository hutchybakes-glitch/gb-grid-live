-- One row per national half-hour that has both a forecast and an actual.
-- error = actual - forecast, so a positive error means the forecast was too low.
-- These are "final forecast vs actual" (the API keeps only the latest forecast
-- for past periods); true day-ahead accuracy comes from snapshots instead.
with wind as (
    select period_start_utc, perc as wind_perc
    from {{ ref('silver_generation_mix') }}
    where fuel = 'wind'
)
select
    n.period_start_utc,
    n.forecast_gco2_kwh,
    n.actual_gco2_kwh,
    n.actual_gco2_kwh - n.forecast_gco2_kwh as error_gco2_kwh,
    abs(n.actual_gco2_kwh - n.forecast_gco2_kwh) as abs_error_gco2_kwh,
    t.local_date,
    t.local_hour,
    t.local_month,
    w.wind_perc,
    -- Fixed, easy-to-explain thresholds on wind's share of generation.
    case
        when w.wind_perc is null then 'unknown'
        when w.wind_perc < 20 then 'low wind (<20%)'
        when w.wind_perc < 40 then 'medium wind (20-40%)'
        else 'high wind (40%+)'
    end as wind_regime
from {{ ref('silver_ci_national') }} n
join {{ ref('dim_time') }} t using (period_start_utc)
left join wind w using (period_start_utc)
where n.actual_gco2_kwh is not null
  and n.forecast_gco2_kwh is not null
