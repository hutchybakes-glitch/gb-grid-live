-- One row per Carbon Intensity region (1-18), with names taken from the API and
-- the matching PV_Live area joined by name via the GSP group letter.
with latest_names as (
    select region_id, dno_region, short_name,
        row_number() over (partition by region_id order by period_start_utc desc) as rn
    from {{ ref('bronze_ci_regional') }}
)
select
    n.region_id,
    n.short_name,
    n.dno_region,
    case
        when n.region_id between 1 and 14 then 'dno'
        when n.region_id between 15 and 17 then 'nation'
        else 'gb'
    end as region_type,
    a.pes_id as pvlive_pes_id,
    'pes' || a.pes_id as pvlive_area_id,
    a.pes_long_name as pvlive_name
from latest_names n
left join {{ ref('pes_region_map') }} m on m.ci_shortname = n.short_name
left join {{ ref('bronze_pvlive_areas') }} a on a.gsp_group = m.gsp_group
where n.rn = 1
