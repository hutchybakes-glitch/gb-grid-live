-- One row per raw PV_Live tuple, across national (gsp0) and the 14 PES areas.
-- Column positions are looked up from each file's own "meta" list, never assumed.
with raw as (
    select meta, data, filename
    from read_json(
        {{ raw_glob('pvlive_*') }},
        columns = {meta: 'VARCHAR[]', data: 'JSON[]'},
        filename = true
    )
),
rows as (
    select
        filename,
        -- Area comes from the folder name (pvlive_gsp0, pvlive_pes16 ...), because
        -- the id column is called gsp_id in one and pes_id in the other.
        regexp_extract(replace(filename, '\', '/'), 'pvlive_((gsp|pes)[0-9]+)/', 1) as area_id,
        list_position(meta, 'datetime_gmt') - 1 as i_dt,
        list_position(meta, 'generation_mw') - 1 as i_gen,
        list_position(meta, 'updated_gmt') - 1 as i_upd,
        list_position(meta, 'capacity_mwp') - 1 as i_cap,
        unnest(data) as r
    from raw
)
select
    area_id,
    strptime(r ->> ('$[' || i_dt || ']'), '%Y-%m-%dT%H:%M:%SZ') as datetime_gmt,
    try_cast(r ->> ('$[' || i_gen || ']') as double) as generation_mw,
    strptime(r ->> ('$[' || i_upd || ']'), '%Y-%m-%dT%H:%M:%SZ') as updated_gmt,
    try_cast(r ->> ('$[' || i_cap || ']') as double) as capacity_mwp,
    filename as _source_file,
    now() as _loaded_at
from rows
