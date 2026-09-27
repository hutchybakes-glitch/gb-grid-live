{{ config(severity='warn') }}
-- Each complete UTC day should have 48 national half-hours. Gaps are expected
-- from the source; they are flagged here and published via gold_data_gaps.
select cast(period_start_utc as date) as utc_date, count(*) as periods
from {{ ref('silver_ci_national') }}
where cast(period_start_utc as date) < current_date
group by 1
having count(*) <> 48
