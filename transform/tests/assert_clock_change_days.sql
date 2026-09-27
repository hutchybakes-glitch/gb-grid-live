-- Known UK clock changes must have 46 (spring) / 50 (autumn) local half-hours.
with expected(local_date, n) as (
    values (date '2023-03-26', 46), (date '2023-10-29', 50),
           (date '2024-03-31', 46), (date '2024-10-27', 50),
           (date '2025-03-30', 46), (date '2025-10-26', 50),
           (date '2026-03-29', 46), (date '2023-06-01', 48)
)
select e.local_date, e.n, count(t.period_start_utc) as actual
from expected e
left join {{ ref('dim_time') }} t on t.local_date = e.local_date
group by all
having count(t.period_start_utc) <> e.n or any_value(t.local_day_half_hours) <> e.n
