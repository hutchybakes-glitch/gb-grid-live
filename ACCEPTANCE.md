# ACCEPTANCE.md — definition of done

Tick each item in `docs/BUILD_LOG.md` with the evidence (command run and its output).

## Phase 1
- [ ] `python -m pipeline.backfill` runs from a clean clone on Windows and can be stopped and resumed without refetching completed chunks.
- [ ] Raw JSON for both sources exists on disk from 2023-01-01 to today; a summary prints files and row counts per source.
- [ ] `python -m pipeline.snapshot` saves a fw48h national and regional forecast with a `captured_at` timestamp.
- [ ] No request exceeds the 14-day range limit; requests are rate-limited.
- [ ] `pytest` passes with no network access.

## Phase 2
- [ ] `python -m pipeline.run` (or documented equivalent) builds all dbt models end to end.
- [ ] All dbt tests pass, or failing checks are warnings that are explained in the build log.
- [ ] `silver_ci_national` has one row per half-hour; gaps are counted and listed.
- [ ] PV_Live revisions are deduplicated to the latest version.
- [ ] Clock-change days show 46 / 50 local half-hours in `dim_time`.

## Phase 3
- [ ] `npm run build` in `web/` succeeds; the built site works from a static file server.
- [ ] Now page shows the current intensity, band name, generation mix and a clickable GB map; default region North West.
- [ ] Best-window finder returns the correct window (verified against a unit test with a known series).
- [ ] Pages are usable at 360px width; Lighthouse accessibility score ≥ 90.
- [ ] Playwright smoke test opens every page without console errors.

## Phase 4
- [ ] Trust page shows official forecast error with a correct MAE calculation (unit-tested) and explains vintages.
- [ ] Model backtest uses rolling-origin evaluation with no data leakage (features only use information available at forecast time); results and baseline shown side by side.
- [ ] Every number in insight cards is computed from gold tables, not typed.
- [ ] How it works page shows live pipeline health from `gold_pipeline_health`.

## Phase 5
- [ ] GitHub Actions run succeeds on a schedule and deploys the site.
- [ ] Public URL loads in under 2 seconds on a normal connection.
- [ ] README explains the project in 3 sentences, with screenshots and setup steps.
