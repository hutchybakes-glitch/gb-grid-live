-- Silver must hold the most recent revision of every PV_Live value.
select s.area_id, s.period_start_utc, s.updated_gmt, max(b.updated_gmt) as newest
from {{ ref('silver_pvlive') }} s
join {{ ref('bronze_pvlive') }} b
  on b.area_id = s.area_id and b.datetime_gmt = s.period_end_utc
group by all
having max(b.updated_gmt) > s.updated_gmt
