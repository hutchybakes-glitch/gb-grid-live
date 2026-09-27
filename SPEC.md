# SPEC.md — GB Grid Live

## One-line purpose
**"When is the cleanest time to use electricity where I live — and how far can you trust the forecast?"**

Every screen must help answer that question. If a feature does not, it is out of scope.

## Audiences
1. **The public** (primary user): picks a region, sees how clean the grid is now and over the next 48 hours, and finds the best window for a task (EV charge, washing, dishwasher).
2. **Hiring managers** (primary reviewer): need to see the method — pipeline, data quality, modelling and honest evaluation — within 90 seconds.

## Pages

### 1. Now (landing page)
- Region selector (default **North West England**, region id 3), remembered for the session.
- Big headline: current carbon intensity (gCO₂/kWh) with its band (very low … very high) in words, not only colour.
- Generation mix for that region right now (donut or stacked bar).
- GB map of the 14 regions coloured by current intensity; click a region to select it.
- One plain-English sentence, e.g. "The North West is cleaner than the GB average right now, mainly thanks to wind."

### 2. Plan (the tool)
- 48-hour forecast line for the chosen region, with the cleanest windows highlighted.
- **Best-window finder**: choose a task (preset durations: EV 4h, washing machine 2h, dishwasher 2h, custom) and it returns the start time with the lowest average intensity, plus how much CO₂ that saves versus starting now (using a stated kWh assumption per task).
- Times displayed in UK local time with clear labels.

### 3. Trust (forecast accuracy)
- NESO publishes a national forecast and, later, an actual. Show how accurate the official forecast is: error over time, error by time of day, and by weather-type periods (high wind vs low wind).
- **Our model**: an error-correction model that predicts national actual intensity from the official forecast plus recent error, solar output and calendar features. Compare it honestly to the official forecast with a rolling backtest. If it does not beat NESO, say so — the honest comparison is the point.
- A clear note on forecast vintages (see `DATA.md`): true day-ahead accuracy is only measurable from snapshots collected by this project, and the page shows how many days of snapshots exist.

### 4. Explore (insight)
- Calendar heatmap: average national intensity by hour of day × month.
- Regional league table: cleanest to dirtiest regions over the last 30 / 365 days.
- **Hidden solar story**: solar generation (PV_Live) plotted against demand — most rooftop solar is invisible to the grid operator and shows up as lower demand. Show the national solar peak and its effect on intensity.
- Three headline insight cards generated from the data (numbers computed, never hard-coded).

### 5. How it works (the method)
- A pipeline diagram: sources → raw → bronze → silver → gold → model → site, with schedule and test counts.
- Data quality panel: last refresh time per source, row counts, test results, known gaps.
- Model card: approach, features, backtest results, limitations, when not to trust it.
- Links to the repo, `DECISIONS.md` and `BUILD_LOG.md`, plus a short "How this was built with Claude Code" section (what the AI did, what the human reviewed and changed).

## Global UX rules
- Understandable within 10 seconds by a non-expert. Each page has a one-sentence subtitle saying what it is for.
- Every chart has a title that states the finding, units on axes, and a tooltip.
- A "Data last updated" badge in the header.
- Works well on mobile (≥ 360px wide) and desktop.
- Footer: data credits and licences, "independent project, not affiliated with NESO or Sheffield Solar".

## Out of scope (v1)
- Electricity prices or tariffs, user accounts, notifications, any backend server, Northern Ireland.
