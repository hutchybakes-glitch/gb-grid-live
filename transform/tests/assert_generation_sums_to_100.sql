-- National generation percentages in each half-hour must sum to 100 +/- 1.
select period_start_utc, sum(perc) as total
from {{ ref('silver_generation_mix') }}
group by period_start_utc
having abs(sum(perc) - 100) > 1
