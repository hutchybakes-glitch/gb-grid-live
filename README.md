# GB Grid Live

*Use power when the grid is cleanest.* An independent portfolio project that shows when electricity in each GB region is cleanest, and how far the official carbon-intensity forecast can be trusted.

> Status: Phase 1 (ingestion) of 5. See `PHASES.md` and `docs/BUILD_LOG.md`.

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
| `python -m pipeline.backfill` | Downloads raw data for both sources from 2023-01-01 to today, in 14-day chunks at no more than one request per second. Safe to stop (Ctrl+C) and rerun: chunks already on disk are skipped. Options: `--start YYYY-MM-DD`, `--end YYYY-MM-DD`, `--sources ci_national pvlive_gsp0 ...` |
| `python -m pipeline.snapshot` | Saves today's 48-hour national and regional forecasts with a `captured_at` time. Run once a day. |
| `python -m pipeline.summary` | Prints files, rows and date coverage per raw source. |
| `python -m pytest` | Runs the unit tests (offline; network access is blocked). |

Raw responses are written to `data/raw/<source>/<chunk-start-date>/` (gitignored). The full backfill makes about 1,400 requests and takes roughly 30–60 minutes.

## Data sources and credits
- **Carbon Intensity API**, NESO, CC BY 4.0: https://carbonintensity.org.uk
- **PV_Live**, Sheffield Solar (University of Sheffield), funded by NESO: https://www.solar.sheffield.ac.uk/pvlive/

Independent project, not affiliated with NESO or Sheffield Solar.
