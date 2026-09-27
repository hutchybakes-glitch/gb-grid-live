# DECISIONS.md

## 2026-09-27 — Live API docs checked against DATA.md

Checked https://carbon-intensity.github.io/api-definitions/ and https://api.solar.sheffield.ac.uk/pvlive/gdocs, plus a handful of live probe requests.

**Confirmed:** CI `/intensity`, `/generation` and `/regional/intensity/{from}/{to}` are all limited to **14 days**. `fw48h` exists for national and regional. Datetime format is `YYYY-MM-DDThh:mmZ`. PV_Live base URL, `meta`/`data` tuple format, `extra_fields=updated_gmt,capacity_mwp` and 30-minute-only resolution are all as described.

**Differences from DATA.md / gotchas found:**
1. **CI `{from}` returns the period that *ends* at `from`.** A request starting at `2023-01-01T00:00Z` returns `2022-12-31T23:30Z–00:00Z` first, so consecutive chunks overlap by one period. Decision: keep raw responses as they are; deduplicate on `from` in silver (Phase 2).
2. **CI regional responses include `shortname`** (for example "North West England") as well as `dnoregion`. `dim_region` will use both.
3. **PV_Live `datetime_gmt` is the period *end*** (as in the Python reference library), and rows come back newest first. Decision: convert to `period_start_utc = datetime_gmt - 30 min` in silver, and never rely on row order.
4. **PV_Live PES ids are 10–23, not 1–14** (from `pes_list`, which also includes 0 = national). They do not share numbering with CI region ids. Decision: fetch `pes_list` at run time, save it as raw JSON, and build a PES↔CI region mapping in Phase 2 using names, not guessed ids.
5. **PV_Live has no stated maximum range, but it has a 30 s request timeout and per-minute throttling (HTTP 429).** Decision: use the same ≤14-day chunks as CI for simple, resumable bookkeeping. Treat 429 as retryable with backoff.
6. `updated_gmt` shows 2023 data was revised as recently as 2026, which confirms the "revisions" note in DATA.md.

## 2026-09-27 — Python version
The machine has Python 3.13.6, which meets the 3.11+ requirement. Dependencies are pinned in `requirements.txt`.

## 2026-09-27 — Chunking and resume
- **Decision:** chunks are anchored at 2023-01-01 in fixed 14-day steps, and the backfill stops at 00:00 UTC today. A chunk is "done" when its file exists. Files are written atomically (temp file, then rename), so an interrupted run cannot leave a half-file that looks finished.
- **Options considered:** (a) a state/manifest file; (b) file existence as the marker. I chose (b) because it is simpler and needs no extra state to go stale.
- **Trailing chunk:** the last chunk is usually shorter than 14 days. The next day's run writes a longer file with the same start date and deletes the shorter one (`stale_siblings`), so the raw folder never accumulates overlapping partial chunks.
- **Snapshots are the exception:** they are never deleted or overwritten. Each run writes a new file named after its `captured_at` minute.

## 2026-09-27 — Failures and empty responses
- A chunk that still fails after 5 attempts (backoff 2, 4, 8, 16 s; retries on 429 and 5xx) is logged and skipped. The run continues and exits with code 1 at the end, listing every failed chunk. Rerunning the backfill fetches only those chunks.
- 4xx errors other than 429 are not retried, because they won't succeed on a second try.
- Responses with no records are never written, so good data can't be replaced with nothing.

## 2026-09-27 — Rate limit shared per client, requests are sequential
Each API client has its own ≥1 s limiter and requests run one after another, so no more than one request per second goes to each host. I chose sequential over concurrent requests: the backfill runs once and the extra speed isn't worth the load on free APIs.

## 2026-09-27 — Snapshot start time
`fw48h` is requested from the current half-hour, rounded down. Because of the `{from}` behaviour noted above, the first period returned is the one just finished. That is harmless, and Phase 2 can filter it out using `captured_at`.

## 2026-09-27 — Only httpx and pytest pinned for Phase 1
DuckDB, dbt, pandas and the modelling libraries will be added in the phase that first needs them, keeping Phase 1 installs small and quick.

## 2026-09-27 — Regional chunks are 13 days, not 14 (found during backfill)
- **What happened:** during the first full backfill, all 98 regional chunks failed with HTTP 400: "The date range you have specified is greater than 14 days". An exact 14-day window (`2023-01-01T00:00Z/2023-01-15T00:00Z`) is accepted by `/intensity` and `/generation` but rejected by `/regional/intensity`. Probes showed that any window up to `…/2023-01-14T23:30Z` works.
- **Decision:** regional uses 13-day chunks (`REGIONAL_CHUNK_DAYS`). All other sources keep 14 days, so their completed files stay valid. This corrects DATA.md's "assume the same 14-day limit": the regional limit is effectively under 14 days.
- **Options considered:** 13 days for every source (simpler, but it would have meant refetching about 200 completed national and generation chunks); ending windows at 23:30 (fiddly, and not the same chunk scheme as the other sources).
- The fixed failure mode worked as designed: nothing was written, the errors were logged, and the rerun fetched only the regional chunks.

## 2026-09-27 — Answers to Phase 1 questions (Samuel: "go with what you think is best")
- **PES to CI region mapping:** built in Phase 2 by matching names from `pes_list` against CI `dnoregion`/`shortname`, with a test that all 14 areas map one-to-one. Hard-coded ids were rejected because DATA.md says to look ids up, not guess them.
- **Daily job:** `snapshot` and `backfill` stay as separate commands. The Phase 5 scheduled workflow will run both (backfill first, which only fetches the newest chunk, then snapshot). Combining them now would add scheduling logic before Phase 5 needs it.
- **learning/:** extended to cover `pvlive.py`, `storage.py` and `snapshot.py`, so every Phase 1 module with real logic has a study copy.


## 2026-09-27 — Phase 2 decisions
- **Backfill now runs up to the current half-hour, and chunks ending in the last 2 days are refetched on every run** (`REFRESH_RECENT_DAYS`). Without this, the freshness test could never pass, and periods fetched just after they ended would keep null `actual` values forever. Refetching an existing file with an empty response never overwrites it (unit-tested). Rejected alternative: a separate "latest" fetcher, which would mean two code paths.
- **Bronze reads raw JSON directly with DuckDB `read_json` and explicit column types** instead of a Python loader. There is one less moving part, and the types are pinned so API additions cannot silently change schemas. Bronze is rebuilt in full each run; this takes about 40 s at this data size.
- **Regional generation mix is kept as a list in bronze and unnested in silver** (`silver_generation_mix_regional`), which keeps bronze about 9x smaller.
- **Silver dedup rules:** national prefers the copy that has an `actual`, then the newest file. Regional and generation keep the newest file. PV_Live keeps the greatest `updated_gmt`. All three are covered by dbt tests (two are dbt unit tests with synthetic revisions).
- **PV_Live `datetime_gmt` is treated as the period end**, so `period_start_utc = datetime_gmt - 30 min`. This matches the Sheffield Solar convention and makes PV_Live join cleanly with Carbon Intensity periods.
- **PES to region mapping:** the seed `pes_region_map.csv` maps the standard GSP group letters (`_A`...`_P`, from `pes_list.pes_name`) to CI `shortname`. Both sides are joined by name, not by id. Test: all 14 DNO regions map one-to-one.
- **Clock-change detection** counts local half-hours from local midnight to the next local midnight, not by counting rows, so partial days at the edges of the range are correct.
- **Completeness and freshness tests have severity `warn`**, as DATA.md specifies. Gaps are published through `gold_data_gaps` and `gold_pipeline_health`.
- **No dbt packages** (such as dbt_utils): the two generic tests needed are 10 lines of macros, and the build then needs no network access.
- **dbt schemas are named after layers** (`bronze.`, `silver.`, `dim.`, `gold.`, `ref.`) via `generate_schema_name`.
- **`gold_region_now` and `gold_region_48h` come from the latest forecast snapshot**, because the site needs a forecast and ranged history is only as fresh as the last backfill.


## 2026-09-27 — Phase 3 decisions
- **GB map is a tile map (one square per region, placed roughly geographically), not real boundaries.** Real DNO boundary files would need a separate licence check and credit, and add around 100 KB+. Tiles are equal-sized, so small regions such as London stay clickable. Each tile is a keyboard-accessible button that shows its value as text. Options considered: NESO DNO boundary GeoJSON (more realistic, but heavier, with a licence to check and tiny London), or a plain list (not a map). Could be swapped for real boundaries later; logged as a question.
- **Hash routing (`#/plan`)** instead of a router library: it works on any static host, including GitHub Pages, with no 404 rewrites, and needs no extra dependency.
- **Vite `base: './'`**, so the same build works from `/`, a Pages project subfolder, or a plain file server.
- **"Now" figures come from the latest forecast snapshot**, not from measured values. Regional data has no actuals, so the page says so under the headline.
- **Best-window finder rules:** it never starts before the current half-hour; ties go to the earliest start; windows spanning a missing half-hour are skipped. Stated kWh assumptions: EV 28 kWh (7 kW × 4 h), washing machine 1 kWh, dishwasher 1.2 kWh, custom = user input. Saving = (average if started now − best average) × kWh.
- **Region choice is stored in `sessionStorage`** ("remembered for the session", per SPEC). The theme is stored in `localStorage`. Both are wrapped in try/catch, so blocked storage doesn't break the page.
- **Only the ECharts parts that are used are imported.** The bundle is still 870 KB (286 KB gzipped); Lighthouse performance on simulated slow 4G is 32 (Now) and 54 (Plan). Accessibility, the Phase 3 criterion, is 100. Load time is a Phase 5 criterion and is noted there.
- **Playwright runs against the production build**, with a second mode (`STATIC_SERVER=python`) using `python -m http.server` to prove the site works from a plain static file server.
- **`pipeline.run` exports JSON only if `dbt build` succeeded**, so a failing data test can never publish bad data to the site.
- **Site data JSON (`web/public/data/`) is committed**, so a fresh clone builds and runs without the warehouse.
