-- One row per source: size, coverage, duplicates removed and gaps. Feeds the
-- data quality panel on the How it works page.
with silver_stats as (
    select 'ci_national' as source, count(*) as silver_rows, count(distinct 'national') as areas,
        min(period_start_utc) as first_period, max(period_start_utc) as last_period
    from {{ ref('silver_ci_national') }}
    union all
    select 'ci_generation', count(distinct period_start_utc), 1, min(period_start_utc), max(period_start_utc)
    from {{ ref('silver_generation_mix') }}
    union all
    select 'ci_regional', count(*), count(distinct region_id), min(period_start_utc), max(period_start_utc)
    from {{ ref('silver_ci_regional') }}
    union all
    select 'pvlive', count(*), count(distinct area_id), min(period_start_utc), max(period_start_utc)
    from {{ ref('silver_pvlive') }}
),
bronze_stats as (
    select 'ci_national' as source, count(*) as bronze_rows, count(distinct _source_file) as raw_files
    from {{ ref('bronze_ci_national') }}
    union all
    -- Generation bronze has one row per fuel; count distinct periods per file instead.
    select 'ci_generation', count(distinct (_source_file, period_start_utc)), count(distinct _source_file)
    from {{ ref('bronze_ci_generation') }}
    union all
    select 'ci_regional', count(*), count(distinct _source_file)
    from {{ ref('bronze_ci_regional') }}
    union all
    select 'pvlive', count(*), count(distinct _source_file)
    from {{ ref('bronze_pvlive') }}
),
gap_stats as (
    select source, count(*) as missing_periods, count(distinct utc_date) as days_with_gaps
    from {{ ref('gold_data_gaps') }}
    group by source
),
snapshots as (
    select
        count(distinct cast(captured_at as date)) as snapshot_days,
        min(captured_at) as first_snapshot,
        max(captured_at) as last_snapshot
    from {{ ref('bronze_forecast_snapshots') }}
)
select
    s.source,
    b.raw_files,
    b.bronze_rows,
    s.silver_rows,
    b.bronze_rows - s.silver_rows as duplicates_removed,
    s.areas,
    s.first_period,
    s.last_period,
    coalesce(g.missing_periods, 0) as missing_periods,
    coalesce(g.days_with_gaps, 0) as days_with_gaps,
    round(100.0 * s.silver_rows / (s.silver_rows + coalesce(g.missing_periods, 0)), 3) as completeness_pct,
    sn.snapshot_days,
    sn.first_snapshot,
    sn.last_snapshot,
    now() as built_at_utc
from silver_stats s
join bronze_stats b using (source)
left join gap_stats g using (source)
cross join snapshots sn
