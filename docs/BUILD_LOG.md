# BUILD_LOG.md

## Session 1 — 2026-09-27 — Phase 1: foundations and ingestion

### What was built
- Repo skeleton: `pipeline/`, `pipeline/ingest/`, `tests/` (with recorded fixtures), `learning/`, `docs/`, `.gitignore`, `requirements.txt` (httpx, pytest pinned), and a README with PowerShell setup steps.
- `pipeline/http.py`: shared httpx client with a ≥1 s rate limiter, 5 attempts with exponential backoff (2/4/8/16 s) on 429/5xx/network errors, and no retry on other 4xx.
- `pipeline/ingest/carbon_intensity.py` and `pipeline/ingest/pvlive.py`: one client per source. PV_Live rows are read through `meta`, never by position.
- `pipeline/backfill.py`: resumable, idempotent backfill from 2023-01-01 to 00:00 UTC today. A chunk counts as done if its file exists; files are written atomically, and empty responses are never written.
- `pipeline/snapshot.py`: daily fw48h national and regional snapshots with `captured_at`.
- `pipeline/summary.py`: files, rows and coverage per source.
- `learning/`: line-by-line commented copies of `chunks.py`, `http.py` and `backfill.py`.

### What broke and how it was fixed
1. **Regional endpoint rejects exact 14-day windows (HTTP 400).** All 98 regional chunks failed on the first full run; nothing was written. Fixed with 13-day regional chunks (see DECISIONS.md), a new test, and a regional-only rerun: 105/105 fetched, 0 failed. The first run's exit code 1 comes from these 97 failures. One old-scheme 7-day regional file (`2026-09-20`) had succeeded on retry; it was fully covered by the new 13-day chunk, so I deleted it.
2. **A bash heredoc** used for writing several files at once failed to parse; I wrote the files individually instead. No code impact.
3. **`python -m venv` in the clean-clone test** printed an `ensurepip` error, but the venv, pip and httpx installed correctly and the backfill ran. The error only happens in the long scratchpad temp path; creating `.venv` in the repo gave no error. Worth watching on a fresh machine.

### Phase 1 acceptance checks

- [x] **`python -m pipeline.backfill` runs from a clean clone on Windows and can be stopped and resumed without refetching completed chunks.**
  Evidence: `git clone` into a temp folder, then `python -m venv .venv`, `pip install -r requirements.txt`, then `python -m pipeline.backfill --start 2023-01-01 --end 2023-04-01 --sources ci_national`, stopped with `Stop-Process` after 6 s:
  ```
  INFO == ci_national: 7 chunks ==
  INFO ci_national ci_national_20230101T0000Z_20230115T0000Z.json: 673 rows
  ... (4 chunks written)
  files on disk after kill: 4
  --- run 2 (resume) ---
  INFO ci_national ci_national_20230226T0000Z_20230312T0000Z.json: 673 rows
  INFO ci_national ci_national_20230312T0000Z_20230326T0000Z.json: 673 rows
  INFO ci_national ci_national_20230326T0000Z_20230401T0000Z.json: 289 rows
  INFO done: fetched 3, skipped 4 existing, empty 0, failed 0
  files on disk after resume: 7
  tmp files: 0
  ```
  Full-range rerun in the main repo after the backfill: `INFO done: fetched 0, skipped 1771 existing, empty 0, failed 0`, exit 0.

- [x] **Raw JSON for both sources exists on disk from 2023-01-01 to today; a summary prints files and row counts per source.**
  `python -m pipeline.summary`:
  ```
  source                files      rows  first period          last period
  ci_generation            98     63853  2022-12-31T23:30Z     2026-09-26T23:30Z
  ci_national              98     65495  2022-12-31T23:30Z     2026-09-26T23:30Z
  ci_regional             105     64005  2022-12-31T23:30Z     2026-09-26T23:30Z
  forecast_snapshots        2       194  2026-09-27T17:30Z     2026-09-29T17:30Z
  pvlive_gsp0              98     65618  2023-01-01T00:00:00Z  2026-09-27T00:00:00Z
  pvlive_pes10 … pes23     98     65618  (each)  2023-01-01T00:00:00Z  2026-09-27T00:00:00Z
  pvlive_reference          1        15  -                     -
  ```
  Notes: "today" means up to 00:00 UTC today (whole days only); today's partial day will be picked up tomorrow. CI rows include a one-period overlap per chunk (the `{from}` behaviour). Expected CI rows with no gaps ≈ 65,618 (14-day) / 65,625 (regional). So the API is missing about **123 national, ~1,765 generation and ~1,620 regional periods**. These are gaps at source, not failed requests; Phase 2 will count and list them.

- [x] **`python -m pipeline.snapshot` saves a fw48h national and regional forecast with a `captured_at` timestamp.**
  ```
  INFO national snapshot: 97 periods -> ...\forecast_snapshots\2026-09-27\fw48h_national_20260927T1813Z.json
  INFO regional snapshot: 97 periods -> ...\forecast_snapshots\2026-09-27\fw48h_regional_20260927T1813Z.json
  exit=0
  fw48h_national_20260927T1813Z.json 2026-09-27T18:13:20Z 97 2026-09-27T17:30Z
  fw48h_regional_20260927T1813Z.json 2026-09-27T18:13:20Z 97 2026-09-27T17:30Z
  ```

- [x] **No request exceeds the 14-day range limit; requests are rate-limited.**
  - `range_path` and `PVLiveClient.fetch_range` raise before sending if a window is too long (tests `test_ci_range_path_format_and_limit`, `test_ci_regional_limit_is_13_days`, `test_pvlive_rejects_oversize_range`); `test_chunks_never_exceed_14_days_and_cover_range` covers the full 2023→2026 range.
  - Rate limiter: `test_rate_limiter_spaces_calls` (sleeps 0.75 s then 1.0 s as expected).
  - From the logs: 1,765 requests in the main run, median gap **1.001 s**; 105 regional requests, median gap 2.6 s. The smallest gap between *log lines* is 0.047 s, because httpx logs when a response *arrives*; the limiter spaces the *sends*.
  - Caveat: the 97 regional 400s in the first run were sent with exact 14-day windows. The API itself counts those as "greater than 14 days", which is why the regional limit is now 13.

- [x] **`pytest` passes with no network access.**
  `tests/conftest.py` patches `socket.connect` and `socket.create_connection` to raise for every test; clients use `httpx.MockTransport` with recorded fixtures.
  ```
  python -m pytest -q
  27 passed in 4.10s
  ```

### What Samuel should review
1. The **regional 13-day decision** and the DATA.md correction (DECISIONS.md).
2. **Resume design:** "file exists = done", plus deleting the shorter trailing chunk (`raw_paths.stale_siblings`). Check you're happy it never deletes snapshots (it doesn't; they live in a separate folder with different naming).
3. The **source gaps** in the summary (~1.7k generation and regional periods missing from the API) before Phase 2 decides how to report them.

### Questions for Samuel
All three Phase 1 questions were answered "go with what you think is best"; decisions are recorded in DECISIONS.md (PES mapping by name in Phase 2; snapshot + backfill combined in the Phase 5 workflow; learning/ extended to pvlive, storage and snapshot). No open questions.


---

## Session 2 — 2026-09-27 — Phase 2: warehouse and data quality

Samuel asked for Phases 2–4 to run back to back, stopping only if blocked or when a decision is needed, and stopping before Phase 5.

### What was built
- dbt-duckdb project in `transform/` (profile in the repo, no secrets; paths set by `pipeline.run`).
- **Bronze:** `bronze_ci_national`, `bronze_ci_generation`, `bronze_ci_regional`, `bronze_pvlive`, `bronze_pvlive_areas`, `bronze_forecast_snapshots`, each with `_source_file` and `_loaded_at`.
- **Silver:** `silver_ci_national`, `silver_ci_regional`, `silver_generation_mix`, `silver_generation_mix_regional`, `silver_pvlive`.
- **Dims:** `dim_region` (from the API, plus the PV_Live area mapped by name), `dim_time` (UTC half-hours, UK local time, clock-change flag).
- **Gold:** `gold_pipeline_health`, `gold_data_gaps`, `gold_region_now`, `gold_region_48h`.
- **Tests:** 43 data tests (generic and singular) and 2 dbt unit tests. Completeness and freshness are `warn`.
- `python -m pipeline.run`: backfill, snapshot, `dbt build`, and a test summary written to `data/dbt_test_results.json`.
- Backfill change: runs to the current half-hour and refetches chunks ending in the last 2 days (2 new pytest tests; 29 pytest tests in total).

### What broke and how it was fixed
- `local` is a reserved word in DuckDB: I renamed the CTE.
- Counting clock-change days by rows would have mislabelled the partial first and last days; I switched to calendar arithmetic.
- dbt 1.12 deprecation warning for generic test arguments: I moved them under `arguments:`.
- Printing DuckDB tables in the Windows console hit a cp1252 encoding error. It only affected my evidence queries (I used plain-text output); no pipeline impact.
- Multi-line bash heredocs containing apostrophes fail in this shell wrapper, so doc updates are written as files instead. No code impact.

### Phase 2 acceptance checks
- [x] **`python -m pipeline.run` builds all dbt models end to end.**
  ```
  INFO done: fetched 19, skipped 1753 existing, empty 0, failed 0
  INFO national snapshot: 97 periods -> ...fw48h_national_20260927T1901Z.json
  INFO regional snapshot: 97 periods -> ...fw48h_regional_20260927T1901Z.json
  Done. PASS=63 WARN=1 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=64
  INFO dbt build success=True; tests: {'pass': 43, 'warn': 1}
  exit=0  elapsed=73s
  ```
- [x] **All dbt tests pass, or failing checks are warnings explained here.** 1 warning: `warn_national_daily_completeness`, 4 UTC days with fewer than 48 national half-hours. These are gaps in the source, not pipeline losses: the raw files don't contain these periods either (see the next item). All other tests pass, including intensity 0–1000, generation sums 100 ± 1 (national and regional), solar ≥ 0 and ≤ capacity, unique and not-null keys on every silver table, and freshness.
- [x] **`silver_ci_national` has one row per half-hour; gaps are counted and listed.**
  ```
  n_rows | distinct_periods | min              | max
  65435  | 65435            | 2023-01-01 00:00 | 2026-09-27 18:00
  gold_data_gaps (ci_national): 2023-10-20: 4 | 2023-10-21: 48 | 2023-10-22: 39 | 2024-06-11: 2 | 2024-06-12: 29   (122 total)
  ```
  `gold_pipeline_health`:
  ```
  source        | raw_files | bronze_rows | silver_rows | dups_removed | areas | missing | days_with_gaps | complete%
  ci_generation |        98 |       63890 |       63796 |           94 |     1 |    1761 |             46 |    97.314
  ci_national   |        98 |       65532 |       65435 |           97 |     1 |     122 |              5 |    99.814
  ci_regional   |       106 |     1152774 |     1150920 |         1854 |    18 |   29106 |             43 |    97.533
  pvlive        |      1470 |      984825 |      983355 |         1470 |    15 |       0 |              0 |   100.0
  ```
  (Regional missing = 1,617 half-hours × 18 regions.)
- [x] **PV_Live revisions are deduplicated to the latest version.** The dbt unit test `pvlive_keeps_latest_revision_and_shifts_to_period_start` (two revisions → the newer one kept, `n_versions = 2`) passes. The singular test `assert_pvlive_keeps_latest_revision` passes against real data, as does `unique_combination(area_id, period_start_utc)`. In the real raw data, the 1,455 keys with 2 versions are chunk-boundary overlaps; true revisions will build up as recent chunks are refetched.
- [x] **Clock-change days show 46 / 50 local half-hours in `dim_time`.**
  ```
  2023-03-26 46 | 2023-10-29 50 | 2024-03-31 46 | 2024-10-27 50 | 2025-03-30 46 | 2025-10-26 50 | 2026-03-29 46
  ```
  Also covered by the singular test `assert_clock_change_days`.

### For Samuel to review (Phase 2)
1. The PES mapping seed `transform/seeds/pes_region_map.csv`, and the resulting `dim_region` (14/14 mapped; e.g. North West England → pes16 ENWL).
2. The change to refetch recent chunks in the backfill (DECISIONS.md).
3. The 1,761 missing generation-mix periods (46 days): larger than the national gaps. The site should say so.
