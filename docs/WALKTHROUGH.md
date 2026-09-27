# 2-minute walkthrough script

For a screen recording or an interview demo. Times are cumulative.

**0:00 – The question (Now page).**
"GB Grid Live answers one question: when is the cleanest time to use electricity where I live, and how far can you trust the forecast? I'm in the North West. Right now the grid here is at [number] grams of CO₂ per kilowatt-hour, which is [band], and the sentence underneath tells me why: mainly wind. The map shows every region; I can click any of them."

**0:20 – The tool (Plan page).**
"If I want to charge an electric car tonight, I pick 'EV charge'. It scans the next 48 hours and finds the four-hour window with the lowest average, and it tells me how much CO₂ I save compared with plugging in now. The energy assumption is stated right there. On a phone it works the same."

**0:45 – Honesty (Trust page).**
"Every figure so far is a forecast, so how good is it? On average NESO's forecast is out by about [MAE] grams, around 7%. It's worst in the morning and evening ramps. I then built an error-correction model and tested it the way it would really be used: train on the past, test on the next month, 33 times over. It beats the official forecast every month. But I'm careful about the claim: history only holds NESO's *final* forecast, so the pipeline also saves the forecast every day, and that will measure true day-ahead accuracy."

**1:20 – Insight (Explore page).**
"The data shows patterns: the grid is cleanest around midday and dirtiest at the evening peak. Scotland runs on almost zero-carbon power while South Wales is the dirtiest region. And this is the hidden-solar story: most solar panels are invisible to the grid operator, but you can see them in the midday dip."

**1:40 – The method (How it works + GitHub).**
"Under the hood it's a daily pipeline on GitHub Actions: two open APIs, raw JSON, then bronze, silver and gold layers in dbt and DuckDB, with around 80 automated data tests. Data quality is published on the site: this table shows every source's gaps, which are counted and never filled in. The repo has a decisions log and a build log that includes what went wrong. I built it with Claude Code from a written spec, and reviewed each phase."

**2:00 – End.**
