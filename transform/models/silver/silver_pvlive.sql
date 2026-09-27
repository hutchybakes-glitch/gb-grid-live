-- Solar outturn: one row per (area, half-hour), latest revision only.
-- PV_Live stamps each value with the END of its half-hour, so shift back 30
-- minutes to match the Carbon Intensity convention of period start.
with ranked as (
    select
        *,
        row_number() over (
            partition by area_id, datetime_gmt
            order by updated_gmt desc, _source_file desc
        ) as rn,
        count(*) over (partition by area_id, datetime_gmt) as n_versions
    from {{ ref('bronze_pvlive') }}
)
select
    area_id,
    datetime_gmt - interval 30 minute as period_start_utc,
    datetime_gmt as period_end_utc,
    generation_mw,
    capacity_mwp,
    updated_gmt,
    n_versions
from ranked
where rn = 1
  and datetime_gmt - interval 30 minute >= timestamp '{{ var("start_date") }}'
