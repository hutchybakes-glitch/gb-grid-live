# PHASES.md — build order

Do one phase per session. At the end of each phase: run the acceptance checks, update `docs/BUILD_LOG.md`, commit locally, and stop with a short summary for Samuel of what to review.

## Phase 1 — Foundations and ingestion
Repo skeleton (folders from `CLAUDE.md`), `.gitignore`, virtual environment, README with Windows setup commands. API clients for Carbon Intensity and PV_Live with retries, caching of raw JSON and polite rate limiting. Resumable backfill from 2023-01-01. Daily snapshot job for fw48h forecasts. Unit tests for the clients (using recorded sample responses, not live calls).

## Phase 2 — Warehouse and data quality
DuckDB + dbt project. Bronze, silver, dim and first gold models from `DATA.md`. All data tests. A `pipeline health` gold table. One command runs the full pipeline end to end.

## Phase 3 — The site: Now and Plan
Vite + React + TypeScript + ECharts app following `DESIGN.md`. JSON export script. Now page (with GB region map) and Plan page (48h forecast, best-window finder). Mobile layout. Playwright smoke test.

## Phase 4 — Trust, Explore and the model
Forecast accuracy analysis, error-correction model with rolling backtest, model card. Explore page with heatmap, regional league table, hidden-solar story and data-driven insight cards. How it works page with pipeline diagram and data quality panel.

## Phase 5 — Automate and publish (needs Samuel)
GitHub Actions workflow: daily pipeline run, tests, JSON export, deploy to GitHub Pages. Before this phase, stop and ask Samuel to create the GitHub repository and confirm he wants to publish. Then: final README with screenshots, a 2-minute walkthrough script, and a polished `docs/BUILD_LOG.md`.
