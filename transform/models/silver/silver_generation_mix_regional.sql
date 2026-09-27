-- Regional generation mix: one row per (region, half-hour, fuel), built from the
-- already-deduplicated regional table so each period has exactly one mix.
with fuels as (
    select region_id, period_start_utc, unnest(generation_mix) as g
    from {{ ref('silver_ci_regional') }}
)
select region_id, period_start_utc, g.fuel as fuel, g.perc as perc
from fuels
