-- The hidden-solar story: average national solar output (PV_Live, mostly
-- rooftop and small sites the grid operator cannot see directly), national
-- demand as the grid sees it (NESO ND) and national carbon intensity through
-- the day, summer vs winter.
with solar as (
    select period_start_utc, generation_mw
    from {{ ref('silver_pvlive') }}
    where area_id = 'gsp0'
),
joined as (
    select
        case when t.local_month in (6, 7, 8) then 'summer'
             when t.local_month in (12, 1, 2) then 'winter'
        end as season,
        hour(t.period_start_local) * 2 + minute(t.period_start_local) // 30 as slot,
        s.generation_mw,
        d.national_demand_mw,
        n.actual_gco2_kwh
    from solar s
    join {{ ref('dim_time') }} t using (period_start_utc)
    left join {{ ref('silver_demand') }} d using (period_start_utc)
    left join {{ ref('silver_ci_national') }} n using (period_start_utc)
)
select
    season,
    slot,
    printf('%02d:%02d', slot // 2, (slot % 2) * 30) as local_time,
    count(*) as n,
    round(avg(generation_mw), 0) as avg_solar_mw,
    round(avg(national_demand_mw), 0) as avg_demand_mw,
    round(avg(actual_gco2_kwh), 1) as avg_actual_gco2_kwh
from joined
where season is not null
group by all
