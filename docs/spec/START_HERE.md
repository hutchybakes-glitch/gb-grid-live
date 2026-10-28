# START HERE — for Samuel

This folder is a build pack. Claude Code reads these files and builds GB Grid Live from them.

## What you need (once)
1. **Python 3.11+** and **Node.js LTS** installed. Check in PowerShell: `python --version` and `node --version`.
2. **Git** installed: `git --version`.
3. **Claude Code** installed and signed in.
4. Use your **personal** laptop, not your work one.

## How to start
1. Put this folder somewhere sensible, e.g. `C:\Users\<you>\Projects\gb-grid-live`.
2. Open PowerShell in that folder and run `git init` (keeps everything local for now).
3. Start Claude Code in the folder (`claude`), and paste the prompt in `KICKOFF_PROMPT.md`.
4. Approve its Phase 1 plan, let it build, and read its summary at the end.
5. Next session, say: **"Read docs/BUILD_LOG.md and start the next phase."**

## Your 20-minute review after each phase
- Open `docs/BUILD_LOG.md`: did every acceptance check actually pass?
- Spot-check the data: does the North West chart look like a real day (cleaner overnight on windy days, a solar dip at midday)?
- Read one file in `learning/` so you can explain it in an interview.
- If something looks wrong, tell Claude Code what you saw; don't fix it silently.

## Decisions already made (change them in the spec files if you disagree)
- Name: GB Grid Live. Default region: North West England.
- Storage: DuckDB + dbt locally (no Databricks in v1, to keep it free and fast).
- Front end: a static React site, later on GitHub Pages.
- Code style: professional comments in the main code, plus line-by-line annotated copies in `learning/` for you.

## GitHub
Not needed until Phase 5. Claude Code will stop and ask before creating or pushing anything. It will use the GitHub login on your own machine — never paste your password or tokens into a chat.
