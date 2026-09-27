-- For each region: the forecast for the half-hour containing the latest
-- snapshot time, with its generation mix and a comparison with GB (region 18).
with latest as (
    select max(captured_at) as captured_at
    from {{ ref('bronze_forecast_snapshots') }}
    where scope = 'regional'
),
now_rows as (
    select s.*
    from {{ ref('bronze_forecast_snapshots') }} s
    join latest l on s.captured_at = l.captured_at
    where s.scope = 'regional'
      and s.captured_at >= s.period_start_utc
      and s.captured_at < s.period_start_utc + interval 30 minute
),
gb as (
    select forecast_gco2_kwh as gb_forecast_gco2_kwh from now_rows where region_id = 18
)
select
    n.region_id,
    r.short_name,
    r.region_type,
    n.period_start_utc,
    n.forecast_gco2_kwh,
    n.intensity_index,
    gb.gb_forecast_gco2_kwh,
    n.forecast_gco2_kwh - gb.gb_forecast_gco2_kwh as diff_vs_gb,
    -- The fuel with the largest share, used for the plain-English sentence.
    list_sort(list_transform(n.generation_mix, g -> struct_pack(perc := g.perc, fuel := g.fuel)), 'DESC')[1].fuel as top_fuel,
    n.generation_mix,
    n.captured_at
from now_rows n
join {{ ref('dim_region') }} r on r.region_id = n.region_id
cross join gb
