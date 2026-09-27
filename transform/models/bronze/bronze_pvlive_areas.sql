-- PV_Live's list of PES (DNO licence) areas, as saved by the backfill.
with raw as (
    select meta, data
    from read_json(
        '{{ env_var("GBGL_RAW_DIR", "../data/raw") | replace("\\", "/") }}/pvlive_reference/pes_list.json',
        columns = {meta: 'VARCHAR[]', data: 'JSON[]'}
    )
),
rows as (
    select
        list_position(meta, 'pes_id') - 1 as i_id,
        list_position(meta, 'pes_name') - 1 as i_name,
        list_position(meta, 'pes_longname') - 1 as i_long,
        unnest(data) as r
    from raw
)
select
    cast(r ->> ('$[' || i_id || ']') as integer) as pes_id,
    r ->> ('$[' || i_name || ']') as gsp_group,
    r ->> ('$[' || i_long || ']') as pes_long_name,
    now() as _loaded_at
from rows
