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


---

## Session 2 (cont.) — Phase 3: the site (Now and Plan)

### What was built
- `pipeline/export.py`: writes `regions.json`, `region_now.json`, `region_48h.json`, `pipeline_health.json` and `meta.json` to `web/public/data/` (about 87 KB in total). It refuses to write empty datasets. It's wired into `pipeline.run`, which exports only after a successful `dbt build`.
- `web/`: Vite + React + TypeScript + ECharts, using the DESIGN.md tokens (dark default, light toggle), Inter, and a bottom tab bar under 768 px.
  - **Now:** region selector (default North West England, remembered for the session), headline intensity with the band in words, a plain-English sentence, the generation-mix donut, a clickable tile map of the 14 regions, and a ranked table.
  - **Plan:** 48 h forecast chart with the cleanest window shaded and a "Now" line; best-window finder (EV 4 h, washing machine 2 h, dishwasher 2 h, custom) with CO₂ saved against starting now and the assumptions stated; the forecast also available as a table.
  - Header badge "Data last updated", and a footer with credits, licences and a non-affiliation note.
  - Trust, Explore and How it works are placeholders until Phase 4.
- Tests: 7 Vitest unit tests for the best-window finder, 16 Playwright smoke tests (desktop and 360 px), and 5 new pytest tests for the export (34 pytest tests in total).

### What broke and how it was fixed
- `test` config in `vite.config.ts` failed type-checking under Vite 8, so I moved it to `vitest.config.ts` (which also stops Vitest picking up Playwright specs).
- **`pipeline.run` export crashed** ("Can't open a connection to same database file with a different configuration"): dbt keeps a read-write DuckDB connection open in the same process. The export now opens with the same settings when called from `run`. My first check missed this because I filtered the output with grep, which hid the exit code. I then checked the file timestamps, found the files hadn't been rewritten, and reran unfiltered.
- The 360 px overflow test failed (6 px) after adding the mobile "Updated" badge; shortened it to the time only.
- An oxlint warning showed the Plan forecast series was rebuilt every render; now memoised.
- Lighthouse on Windows prints `EPERM` when deleting its temporary browser profile *after* saving the report. The scores are valid; it's a known Windows cleanup quirk.

### Phase 3 acceptance checks
- [x] **`npm run build` succeeds; the built site works from a static file server.**
  ```
  npm run build  ->  ✓ built in 1.24s  (dist/assets/index-*.js 869.84 kB │ gzip: 286.25 kB)
  STATIC_SERVER=python npx playwright test   ->  16 passed (14.5s)   [python -m http.server --directory dist]
  ```
  I confirmed afterwards that port 4173 was free, so no existing server was reused.
- [x] **Now page shows current intensity, band name, generation mix and a clickable GB map; default region North West.**
  Screenshot check (desktop): "North West England, 20:00–20:30 BST · 10 gCO₂/kWh · Very low · North West England is cleaner than the GB average right now (10 vs 84 gCO₂/kWh), mainly thanks to wind." Donut "Wind is the biggest source right now". Tile map with values.
  Playwright: `Now page defaults to North West England and the map selects a region`: default value `3`; clicking the London tile sets `13`; the choice persists on the Plan page. Passes on desktop and 360 px.
- [x] **Best-window finder returns the correct window (unit test with a known series).**
  `npm test` → `Tests 7 passed (7)`. Series `[100, 90, 80, 50, 10, 20, 60, 70]`: the 2-slot best starts at index 4 (average 15; now 95); the 4-slot best starts at index 3 (average 35); it never starts before now, breaks ties by earliest start, skips gaps, returns null if the task is too long, and CO₂ saved = (95 − 15) × 28.
- [x] **Pages usable at 360 px; Lighthouse accessibility ≥ 90.**
  Lighthouse (Edge headless): **Now a11y 100**, **Plan a11y 100**. The Playwright `mobile-360` project passes every page, including a check for no horizontal scroll.
  (Performance: Now 32, Plan 54 on simulated slow 4G. Not a Phase 3 criterion; to address for Phase 5's load-time target.)
- [x] **Playwright smoke test opens every page without console errors.**
  `npx playwright test` → `16 passed`: every page on desktop and 360 px, checking console errors, page errors, failed requests and HTTP ≥ 400.

### For Samuel to review (Phase 3)
1. The tile map instead of real boundaries (DECISIONS.md). It works well for clicking and accessibility, but it's a design choice you may want to change.
2. The kWh assumptions on the Plan page (EV 28 kWh, washing 1 kWh, dishwasher 1.2 kWh).
3. Wording of the plain-English sentence (`web/src/lib/sentence.ts`).


---

## Session 2 (cont.) — Phase 4: Trust, Explore, the model and How it works

### What was built
- **dbt:** `silver_forecast_errors`, `gold_forecast_accuracy` (overall, month, UK hour, wind regime), `gold_snapshot_accuracy` (true lead-time accuracy from snapshots), `gold_heatmap_hour_month`, `gold_region_league` (30/365 days), `gold_solar_profile`, `gold_insights`. There are now 83 dbt nodes, including 55 data tests (one warn-only) and 3 unit tests; the latest build reports `{pass: 57, warn: 1}`.
- **`pipeline/model/`:** `metrics.py` (MAE/RMSE/bias), `features.py` (leakage-safe features), `backtest.py` (rolling-origin LightGBM backtest for 1 h and 24 h horizons, writing `gold.gold_model_backtest` and `gold.gold_model_features`). `pipeline.run` now does ingest → snapshot → dbt build → backtest → export.
- **Export:** adds `trust.json` (22 KB) and `explore.json` (34 KB).
- **Site:** Trust page (headline MAE, the vintage caveat and snapshot count, monthly error, error by hour, wind regimes, model vs official with a 24 h/1 h toggle, feature importance, and a limitations paragraph); Explore page (3 computed insight cards, hour × month heatmap, the hidden-solar chart and story, region league 30/365 days); How it works (pipeline diagram, live data quality table and test counts from `gold_pipeline_health`, gap list, model card, links to the repo, DECISIONS and BUILD_LOG, and a "built with Claude Code" section).
- **Tests:** 7 new pytest tests (MAE known values, NaN refusal, leakage poisoning at both horizons, the gap-shift check, rolling-origin train/test split, fold months), for 41 pytest tests in total. 1 new dbt unit test (MAE) and 1 new Playwright test (18 in total).
- **learning/:** `backfill.py` synced with the Phase 2 refresh logic; new `features.py`.

### What broke and how it was fixed
- **My hand-written expected values in the MAE dbt unit test were wrong** (I wrote 3.3% for MAE as a share of the mean; the correct value is 10.0% because the mean actual is 100). The test failed and the model was right. I fixed the expectation.
- **dbt's failure message crashed on the Windows console encoding** (cp1252 can't print "→"). `pipeline.run` now reconfigures stdout and stderr to UTF-8.
- **My synthetic data in the rolling-origin test** ended on 29 January, so January had 29 days, not 31. I extended the test data.
- **The test summary skipped dbt unit tests;** it now counts both `test` and `unit_test` nodes.
- **The Explore subtitle said "nearly four years"**, a typed-in number; I replaced it with "since January 2023".

### Phase 4 acceptance checks
- [x] **Trust page shows official forecast error with a correct MAE calculation (unit-tested) and explains vintages.**
  - dbt unit test `forecast_accuracy_mae_is_mean_absolute_error` (errors +10, −20, 0 → MAE 10, bias −3.33, RMSE 12.91, plus per-hour and per-wind groups): **pass**.
  - pytest `test_mae_known_values` (same example via `metrics.mae/bias/rmse`): **pass**.
  - The page states "On average the official forecast is out by 9.8 gCO₂/kWh (7.4% of the typical value)" over 65,387 half-hours. It has a caveat section explaining final forecast vs day-ahead vintages and shows "Snapshots collected so far: 1 day" (Playwright asserts both).
- [x] **Model backtest uses rolling-origin evaluation with no leakage; results and baseline shown side by side.**
  - pytest `test_no_feature_uses_information_after_the_cutoff[2]` and `[48]`: every actual and solar value after a cut-off is set to 1e9, and features for periods ≤ cut-off + horizon are unchanged. **Pass.** `test_missing_period_does_not_shift_wrong_row`: **pass**. `test_rolling_origin_trains_only_on_the_past`: train rows = all rows before 2024-01-01, test = the 1,488 January half-hours. **Pass.**
  - Real backtest, 33 monthly folds (2024-01 to 2026-09), 47,963 test half-hours:
    ```
    1h_ahead  overall MAE: official 9.81 | model 5.67 | official+recent error 8.85
    24h_ahead overall MAE: official 9.81 | model 8.16 | official+recent error 11.24
    ```
    The model beats the official forecast in 33/33 months at both horizons. The Trust page shows the monthly lines and a side-by-side table with both baselines, plus a limitations paragraph (see DECISIONS: final-forecast caveat).
- [x] **Every number in insight cards is computed from gold tables, not typed.** All values come from `gold.gold_insights` (e.g. `cleanest_hour 12.0 | 103.56 | 19.0 | 153.31`, `year_on_year 124.36 | 132.69`, `region_gap 2 | 7.2 | 7 | 251.4`); the site computes % and ratios from those and looks up region names in `regions.json`. dbt tests: `not_null` on `value_1`/`value_2` and `unique` on `card`. Chart titles on Explore and Trust are also computed (e.g. "Cleanest on average: Jun around 13:00 (88 gCO₂/kWh)").
- [x] **How it works page shows live pipeline health from `gold_pipeline_health`.** The table rows come from `pipeline_health.json` (exported from `gold.gold_pipeline_health`) with test counts from the latest `dbt build`. Playwright asserts the "N automated data checks" heading and the "Carbon Intensity: national" row.

Full runs:
```
python -m pipeline.run --skip-ingest   ->  Done. PASS=82 WARN=1 ERROR=0 SKIP=0 TOTAL=83; exports written; exit=0
python -m pytest -q                    ->  41 passed
npm test                               ->  7 passed
npx playwright test                    ->  18 passed
```

### For Samuel to review (Phase 4)
1. **The model claims and caveats** on the Trust page and in the model card. The improvement is large; I've been explicit that it's measured against the *final* forecast.
2. **Solar vs intensity instead of solar vs demand** (no demand source). See the question below.
3. The **wind thresholds** (20% / 40%) and the insight-card wording.

### Questions for Samuel
- Should I add NESO's national demand data (NESO Data Portal, open licence, no key) so the hidden-solar chart can show demand, as SPEC.md describes? I used solar vs intensity for now.


---

## Session 2 (cont.) — Phase 5: automate and publish (the push block below was later resolved)

Samuel created https://github.com/hutchybakes-glitch/gb-grid-live (empty; Pages source is GitHub Actions; workflow permissions read/write) and asked me to add it as the remote, push, set up the daily pipeline and deploy.

### What was built
- `.github/workflows/daily.yml`: runs daily at 05:30 UTC, on manual dispatch, and on push to `main`. Steps: Python tests → `pipeline.run` (ingest, snapshot, dbt build, model, export) → commit new snapshots to the `snapshots` branch → save the raw cache → Vitest, build, Playwright → deploy to GitHub Pages.
- **Storage between runs:** raw API chunks are kept in the Actions cache (re-fetchable; if evicted, the resumable backfill refetches them). **Forecast snapshots are kept on a `snapshots` branch** because they can never be re-downloaded.
- **Snapshots are now gzipped** (`.json.gz`; regional 759 KB → 41 KB, about 15 MB a year). `storage.read_json` reads either format; the bronze glob matches both. I converted the 6 local snapshots and confirmed dbt reads them (3 captures: national 291 rows, regional 5,238).
- README rewritten (3-sentence summary, live URL, screenshots, pipeline sketch, setup); `docs/WALKTHROUGH.md` (2-minute script); `docs/screenshots/`.
- Local branch renamed `master` → `main`; orphan branch `snapshots` created with the existing snapshots.
- `learning/storage.py` and `learning/snapshot.py` synced for gzip.

### Notes
- One snapshot (`…T1859Z`) was created by the `pipeline.run` call that Samuel interrupted earlier; it evidently got as far as the snapshot step before being stopped. It's a genuine capture, so I kept it.

### BLOCKED: push rejected
```
git push -u origin snapshots
remote: Permission to hutchybakes-glitch/gb-grid-live.git denied to sammyhutch.
fatal: ... The requested URL returned error: 403
```
The GitHub credentials stored on this machine belong to the account `sammyhutch`, which has no write access to the `hutchybakes-glitch` repository. Nothing has been pushed. The remote `origin` is configured locally.

### Phase 5 acceptance checks
(Superseded: see "Phase 5: unblocked and deployed" below for the final checks.)


### Update: NESO demand data added (Samuel: "happy to go with your suggestions")
- New source: **NESO Historic Demand Data** (NESO Data Portal, NESO Open Data Licence, no key). `pipeline/ingest/neso_demand.py` reads the dataset listing to find each year's CSV URL (never guessed) and downloads 2023 to the current year: 4 requests, rate-limited, with the shared retries. The current year is refetched every run, and the previous year during January. It's wired into `pipeline.run`.
- dbt: `bronze_neso_demand` (three different date formats across years, `01-Jan-23`, `01-JAN-2024` and `2025-01-01`, all parsed), `silver_demand` (actual rows only; settlement periods converted from UK local time to UTC via local midnight), and `gold_solar_profile` renamed to **`gold_solar_vs_demand`** as DATA.md planned, now with average national demand. Explore's hidden-solar chart now shows demand as the grid sees it: on an average summer day it is 23.3 GW at 08:00 and 21.3 GW at 13:00, when solar peaks at 8.8 GW.
- Tests: dbt unit test `demand_settlement_periods_convert_to_utc_across_clock_change` (spring-forward day and BST day, forecast rows dropped), `unique`, `not_null` and a 5–70 GW range on `silver_demand`, plus 5 pytest tests. Totals: `dbt build` PASS=90 WARN=1 (unchanged warning); pytest 46 passed; Playwright 18 passed.
- **Broke and fixed:**
  - NESO download links redirect to their file storage; the shared HTTP client now follows redirects.
  - **My bug:** saving the CSV in Python text mode on Windows turned `\r\n` into `\r\r\n`, which DuckDB couldn't parse. It now writes with `newline=""`, with a regression test.
  - A `sed` edit mangled a code comment; I repaired it by hand.
- Demand actuals currently run to 2026-09-06: NESO updates the file periodically, not daily.
- The earlier open question about adding demand data is now resolved.


### Phase 5: unblocked and deployed
- Samuel confirmed `hutchybakes-glitch` is the correct account. I set the git author **for this repo only** (`git config --local`): `hutchybakes-glitch <233273153+hutchybakes-glitch@users.noreply.github.com>`, the GitHub no-reply address (the ID came from the public GitHub API). I rewrote all 14 existing local commits on `main` and `snapshots` before anything was pushed, so no `sammyhutch` identity was published. Samuel was given the exact `!` commands to switch the saved login. The push then succeeded:
  ```
  * [new branch]      snapshots -> snapshots
  * [new branch]      main -> main
  ```
- **First Actions run:** [36348433254](https://github.com/hutchybakes-glitch/gb-grid-live/actions/runs/36348433254), triggered by the push. Started 20:32:49Z, finished 21:16:11Z (about 43 minutes, including the full backfill from 2023 on an empty cache). Every step succeeded: Python tests → pipeline → save snapshots (bot commit "Forecast snapshot 2026-09-27T21:14Z" on `snapshots`) → save raw cache → Vitest, build, Playwright → upload → **deploy**.
- **Live site:** https://hutchybakes-glitch.github.io/gb-grid-live/ (HTTP 200; `data/meta.json` exported 2026-09-27T21:14:29Z).

### Phase 5 acceptance checks
- [x] **GitHub Actions run succeeds and deploys the site.** Run 36348433254 finished `success` for both the `build` and `deploy` jobs.
  **Caveat:** that run was triggered by the push. The daily schedule (`cron: 30 5 * * *`) is configured, but the first scheduled run (05:30 UTC on 28 September) hasn't happened yet, so a *scheduled* success isn't yet observed. Check it tomorrow on the Actions tab.
- [x] **Public URL loads in under 2 seconds on a normal connection**, with caveats. Playwright with a fresh browser context each time (cold browser cache), from this PC over home broadband, 3 loads per page:
  ```
  now      load 2882ms / content 3437ms | load 274ms / content 657ms | load 256ms / content 607ms
  plan     load 253ms / content 680ms | load 243ms / content 638ms | load 297ms / content 710ms
  trust    load 283ms / content 826ms | load 258ms / content 725ms | load 269ms / content 735ms
  explore  load 258ms / content 736ms | load 275ms / content 782ms | load 292ms / content 768ms
  how      load 268ms / content 564ms | load 267ms / content 518ms | load 264ms / content 522ms
  ```
  14 of 15 loads were under 1 s to full content, with no console errors. **The very first request after the deploy took 3.4 s**, most likely GitHub Pages' CDN and connection setup warming up (not proven). Lighthouse's *simulated slow-4G mobile* profile on the live site: Now performance 61 (FCP 3.6 s), Plan 55 (FCP 3.5 s); accessibility 100 on both. So the site is fast on a normal connection but not under 2 s on a throttled mobile connection. The main cost is the 286 KB (gzipped) JavaScript bundle, mostly ECharts. Suggested next step: lazy-load the chart-heavy pages and split ECharts into its own chunk.
- [x] **README explains the project in 3 sentences, with screenshots and setup steps.** See `README.md` (3-sentence summary, live URL, 4 screenshots, pipeline sketch, Windows setup, commands, credits).

### What Samuel should review (Phase 5)
1. The first **scheduled** run tomorrow at 05:30 UTC (Actions tab). It should take a few minutes now that the cache exists.
2. The live site on your phone: load speed on mobile data is the weakest point.
3. The `snapshots` branch: a bot commit is added every day; this is intended.
