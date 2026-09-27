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
