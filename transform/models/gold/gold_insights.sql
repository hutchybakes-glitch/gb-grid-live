-- Numbers for the three insight cards on the Explore page. Every value is
-- computed here; the site only fills them into sentences.
with latest as (
    select max(period_start_utc) as t from {{ ref('silver_ci_national') }} where actual_gco2_kwh is not null
),
last_year as (
    select n.*, tm.local_hour
    from {{ ref('silver_ci_national') }} n
    join {{ ref('dim_time') }} tm using (period_start_utc)
    cross join latest l
    where n.actual_gco2_kwh is not null
      and n.period_start_utc > l.t - interval 365 day
),
by_hour as (
    select local_hour, avg(actual_gco2_kwh) as avg_i from last_year group by 1
),
hour_card as (
    select
        'cleanest_hour' as card,
        arg_min(local_hour, avg_i) as value_1,
        min(avg_i) as value_2,
        arg_max(local_hour, avg_i) as value_3,
        max(avg_i) as value_4
    from by_hour
),
trend_card as (
    select
        'year_on_year' as card,
        avg(case when n.period_start_utc > l.t - interval 365 day then n.actual_gco2_kwh end) as value_1,
        avg(case when n.period_start_utc <= l.t - interval 365 day
                  and n.period_start_utc > l.t - interval 730 day then n.actual_gco2_kwh end) as value_2,
        null::double as value_3,
        null::double as value_4
    from {{ ref('silver_ci_national') }} n
    cross join latest l
    where n.actual_gco2_kwh is not null
),
league as (
    select * from {{ ref('gold_region_league') }} where window_days = 365
),
region_card as (
    select
        'region_gap' as card,
        (select region_id from league order by rank limit 1) as value_1,
        (select avg_gco2_kwh from league order by rank limit 1) as value_2,
        (select region_id from league order by rank desc limit 1) as value_3,
        (select avg_gco2_kwh from league order by rank desc limit 1) as value_4
)
select card, round(value_1, 2) as value_1, round(value_2, 2) as value_2,
       round(value_3, 2) as value_3, round(value_4, 2) as value_4,
       (select t from latest) as as_of_utc
from hour_card
union all
select card, round(value_1, 2), round(value_2, 2), value_3, value_4, (select t from latest) from trend_card
union all
select card, value_1, value_2, value_3, value_4, (select t from latest) from region_card
