# GB Grid Live

*Use power when the grid is cleanest.* An independent portfolio project that shows when electricity in each GB region is cleanest, and how far the official carbon-intensity forecast can be trusted.

> Status: see `docs/BUILD_LOG.md` for the current phase.

## Setup (Windows, PowerShell)

```powershell
git clone <repo-url> gb-grid-live
cd gb-grid-live
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Requires Python 3.11+. No API keys are needed.

## Commands

| Command | What it does |
| --- | --- |
| `python -m pipeline.run` | **The whole pipeline:** backfill (only new or recent chunks), forecast snapshot, then `dbt build` (all models and tests) into `data/warehouse.duckdb`. Add `--skip-ingest` to rebuild from raw files without calling the APIs. |
| `python -m pipeline.backfill` | Downloads raw data for both sources from 2023-01-01 to the current half-hour, in 14-day chunks at no more than one request per second. Safe to stop (Ctrl+C) and rerun: chunks already on disk are skipped. Options: `--start YYYY-MM-DD`, `--end YYYY-MM-DD`, `--sources ci_national pvlive_gsp0 ...` |
| `python -m pipeline.snapshot` | Saves today's 48-hour national and regional forecasts with a `captured_at` time. Run once a day. |
| `python -m pipeline.summary` | Prints files, rows and date coverage per raw source. |
| `python -m pytest` | Runs the Python unit tests (offline; network access is blocked). |
| `python -m pipeline.export` | Writes the site's JSON files from the gold tables to `web/public/data/` (also run by `pipeline.run`). |

### Website (in `web/`)
```powershell
cd web
npm install
npm run dev          # local development server
npm run build        # production build into web/dist
npm test             # unit tests (best-window finder)
npx playwright install chromium
npm run e2e          # smoke tests against the production build (desktop and 360px)
```

Raw responses are written to `data/raw/<source>/<chunk-start-date>/` (gitignored). The full backfill makes about 1,400 requests and takes roughly 30–60 minutes.

## Data sources and credits
- **Carbon Intensity API**, NESO, CC BY 4.0: https://carbonintensity.org.uk
- **PV_Live**, Sheffield Solar (University of Sheffield), funded by NESO: https://www.solar.sheffield.ac.uk/pvlive/

Independent project, not affiliated with NESO or Sheffield Solar.
