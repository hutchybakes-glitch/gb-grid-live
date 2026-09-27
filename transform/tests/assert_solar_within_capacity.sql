-- Solar generation must be >= 0 and no more than installed capacity.
select area_id, period_start_utc, generation_mw, capacity_mwp
from {{ ref('silver_pvlive') }}
where generation_mw < 0
   or (capacity_mwp is not null and generation_mw > capacity_mwp)
