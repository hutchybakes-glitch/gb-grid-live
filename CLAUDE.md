# CLAUDE.md — standing rules for this repository

You are building **GB Grid Live**, a public portfolio project by Samuel (Senior Analyst, moving into analytics / data engineering). Read `SPEC.md`, `DATA.md`, `DESIGN.md`, `PHASES.md` and `ACCEPTANCE.md` before any work. They are the source of truth; if they conflict, stop and ask.

## How to work
- Work one phase at a time, as defined in `PHASES.md`. Start each phase in plan mode: summarise what you will build, then build it.
- A phase is finished only when every item for that phase in `ACCEPTANCE.md` passes. Run the checks yourself and paste the results into `docs/BUILD_LOG.md`.
- Never mark something done that you have not run. If a check cannot pass, say so plainly in the build log.
- Record every non-obvious choice in `docs/DECISIONS.md`: date, decision, options considered, why.
- Keep `docs/BUILD_LOG.md` up to date: what was built in each session, what broke, how it was fixed, and what the human should review.

## Environment
- The developer's machine is **Windows**. Write commands for PowerShell and paths that work on Windows. Avoid bash-only scripts; use Python or `make`-free task runners (a `tasks.py` with `invoke`, or plain `python -m` commands documented in the README).
- Python 3.11+ in a project virtual environment (`.venv`). Pin dependencies in `requirements.txt` (or `pyproject.toml`).
- Node.js LTS for the front end.

## Tech stack (do not change without logging a decision)
- Ingestion: Python, `httpx` with retries and backoff, one module per source in `pipeline/ingest/`.
- Storage: DuckDB file at `data/warehouse.duckdb`; raw API responses saved as JSON under `data/raw/<source>/<date>/` (gitignored).
- Transformation: dbt with `dbt-duckdb`, in `transform/`. Layers: `bronze_` (raw, typed), `silver_` (cleaned, deduplicated, conformed UTC timestamps), `gold_` (app-ready marts).
- Modelling: scikit-learn / LightGBM in `pipeline/model/`.
- Export: a script writes small JSON files from gold tables to `web/public/data/`.
- Front end: Vite + React + TypeScript + Apache ECharts in `web/`. A static site with no server.
- Tests: `pytest` for Python, dbt tests for data, a Playwright smoke test for the site.
- Scheduling (Phase 5): GitHub Actions. Hosting: GitHub Pages.

## Code quality
- Type hints and docstrings on every function. Comments explain *why*, not *what*.
- Small, single-purpose functions. No notebooks in the main pipeline (notebooks may live in `analysis/`).
- All times stored and processed in **UTC**; convert to Europe/London only for display.
- Handle API failure gracefully: retries, clear log messages, and never overwrite good data with an empty response.
- Also maintain `learning/`: for each important module, a copy with a plain-English comment above every line, so Samuel can study it. Keep these in sync at the end of each phase.

## Safety and hygiene
- No secrets are needed for this project. Never add API keys, tokens or personal data to the repo.
- Respect the APIs: cache responses, at most ~1 request per second, no pointless polling. Credit sources in the site footer (Carbon Intensity API: CC BY 4.0, NESO; PV_Live: Sheffield Solar / NESO).
- Do not use any company's logo or branding. The project has its own identity (see `DESIGN.md`).
- Do not run `git push`, create remote repositories or publish anything unless the human explicitly asks. Local commits are fine and encouraged: small commits with clear messages.

## When unsure
Prefer the simplest thing that meets the spec, log the question in `docs/BUILD_LOG.md` under "Questions for Samuel", and carry on with a sensible default.
