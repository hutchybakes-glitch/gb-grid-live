-- One row per UTC half-hour from the start date to three days ahead (covers the
-- 48h forecast). Local UK time is derived here and only used for display.
with slots as (
    select unnest(generate_series(
        timestamp '{{ var("start_date") }}',
        cast(current_date + 3 as timestamp),
        interval 30 minute
    )) as period_start_utc
),
loc as (
    select
        period_start_utc,
        timezone('Europe/London', timezone('UTC', period_start_utc)) as period_start_local
    from slots
)
select
    period_start_utc,
    period_start_local,
    cast(period_start_utc as date) as utc_date,
    cast(period_start_local as date) as local_date,
    hour(period_start_local) as local_hour,
    month(period_start_local) as local_month,
    isodow(period_start_local) as local_iso_dow,
    -- 46 on the spring clock change, 50 in autumn, 48 otherwise. Computed from
    -- the calendar (local midnight to next local midnight) so partial days at
    -- the edges of the range are still counted correctly.
    cast((epoch(timezone('Europe/London', cast(cast(period_start_local as date) + 1 as timestamp)))
        - epoch(timezone('Europe/London', cast(cast(period_start_local as date) as timestamp)))) / 1800 as integer)
        as local_day_half_hours,
    cast((epoch(timezone('Europe/London', cast(cast(period_start_local as date) + 1 as timestamp)))
        - epoch(timezone('Europe/London', cast(cast(period_start_local as date) as timestamp)))) / 1800 as integer)
        <> 48 as is_clock_change_day
from loc
