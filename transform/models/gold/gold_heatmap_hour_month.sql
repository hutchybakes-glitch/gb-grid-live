-- Average national carbon intensity (measured actual) by UK local hour and
-- calendar month, across all years in the warehouse.
select
    t.local_month,
    t.local_hour,
    count(*) as n,
    round(avg(n.actual_gco2_kwh), 1) as avg_actual_gco2_kwh
from {{ ref('silver_ci_national') }} n
join {{ ref('dim_time') }} t using (period_start_utc)
where n.actual_gco2_kwh is not null
group by all
