-- Each of the 14 DNO regions must map to exactly one distinct PV_Live PES area.
with m as (
    select count(*) as n, count(distinct pvlive_pes_id) as n_distinct, count(pvlive_pes_id) as n_mapped
    from {{ ref('dim_region') }}
    where region_type = 'dno'
)
select * from m where not (n = 14 and n_distinct = 14 and n_mapped = 14)
