{{ config(severity='warn') }}
-- The latest national period should be within 2 hours of the run.
-- Warn only: an offline rebuild of old raw data will legitimately fail this.
select max(period_start_utc) as latest
from {{ ref('silver_ci_national') }}
having max(period_start_utc) < cast(now() at time zone 'UTC' as timestamp) - interval 2 hour
