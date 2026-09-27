-- Regional generation percentages per (region, half-hour) must sum to 100 +/- 1.
select region_id, period_start_utc, sum(perc) as total
from {{ ref('silver_generation_mix_regional') }}
group by region_id, period_start_utc
having abs(sum(perc) - 100) > 1
