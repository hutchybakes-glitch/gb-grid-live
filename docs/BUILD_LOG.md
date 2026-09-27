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
