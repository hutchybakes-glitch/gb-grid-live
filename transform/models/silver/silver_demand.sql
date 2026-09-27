-- National demand per UTC half-hour (actuals only). NESO settlement periods
-- count from local midnight (period 1 = 00:00-00:30 UK time), so clock-change
-- days have 46 or 50 periods; convert to UTC via local midnight.
with actuals as (
    select *,
        row_number() over (
            partition by settlement_date, settlement_period
            order by _source_file desc
        ) as rn
    from {{ ref('bronze_neso_demand') }}
    where forecast_actual = 'A'
      and settlement_date is not null
      and settlement_period between 1 and 50
)
select
    timezone('UTC',
        timezone('Europe/London', cast(settlement_date as timestamp))
        + to_minutes(30 * (settlement_period - 1))
    ) as period_start_utc,
    settlement_date,
    settlement_period,
    national_demand_mw,
    transmission_demand_mw,
    embedded_solar_mw,
    embedded_solar_capacity_mw
from actuals
where rn = 1
  and settlement_date >= date '{{ var("start_date") }}'
