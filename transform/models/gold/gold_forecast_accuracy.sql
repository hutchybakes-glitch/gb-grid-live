-- Official (final) forecast accuracy, national only, grouped several ways for
-- the Trust page. MAE = mean absolute error; bias = mean(actual - forecast).
with e as (
    select * from {{ ref('silver_forecast_errors') }}
),
grouped as (
    select 'overall' as grouping, 'all' as group_key, count(*) as n,
        avg(abs_error_gco2_kwh) as mae, avg(error_gco2_kwh) as bias,
        sqrt(avg(error_gco2_kwh * error_gco2_kwh)) as rmse,
        avg(actual_gco2_kwh) as mean_actual
    from e
    union all
    select 'month', strftime(local_date, '%Y-%m'), count(*),
        avg(abs_error_gco2_kwh), avg(error_gco2_kwh), sqrt(avg(error_gco2_kwh * error_gco2_kwh)), avg(actual_gco2_kwh)
    from e group by 2
    union all
    select 'local_hour', lpad(cast(local_hour as varchar), 2, '0'), count(*),
        avg(abs_error_gco2_kwh), avg(error_gco2_kwh), sqrt(avg(error_gco2_kwh * error_gco2_kwh)), avg(actual_gco2_kwh)
    from e group by 2
    union all
    select 'wind_regime', wind_regime, count(*),
        avg(abs_error_gco2_kwh), avg(error_gco2_kwh), sqrt(avg(error_gco2_kwh * error_gco2_kwh)), avg(actual_gco2_kwh)
    from e group by 2
)
select
    grouping,
    group_key,
    n,
    round(mae, 2) as mae,
    round(bias, 2) as bias,
    round(rmse, 2) as rmse,
    -- MAE as a share of the average actual, for a plain-English "within X%".
    round(100 * mae / nullif(mean_actual, 0), 1) as mae_pct_of_mean
from grouped
