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
