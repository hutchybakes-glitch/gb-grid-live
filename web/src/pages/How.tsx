import Status, { allReady } from '../components/Status'
import { useData, type PipelineHealth, type Trust } from '../lib/data'
import { ukDateTime, ukZone, whole } from '../lib/format'

const REPO = 'https://github.com/hutchybakes-glitch/gb-grid-live'
const SOURCE_LABEL: Record<string, string> = {
  ci_national: 'Carbon Intensity: national',
  ci_generation: 'Carbon Intensity: generation mix',
  ci_regional: 'Carbon Intensity: regional',
  pvlive: 'PV_Live: solar (national + 14 areas)',
}

const STEPS: { title: string; body: string }[] = [
  { title: 'Sources', body: 'Carbon Intensity API (NESO) and PV_Live (Sheffield Solar). Free, no keys.' },
  { title: 'Raw', body: 'Every API response saved as JSON, in ≤14-day chunks, max 1 request a second.' },
  { title: 'Bronze', body: 'Raw records typed into tables, nothing removed.' },
  { title: 'Silver', body: 'Duplicates removed, UTC half-hours, latest solar revision.' },
  { title: 'Gold', body: 'Small tables shaped for one chart each.' },
  { title: 'Model', body: 'Error-correction model, rolling monthly backtest.' },
  { title: 'Site', body: 'JSON files and a static React site.' },
]

export default function How() {
  const health = useData<PipelineHealth>('pipeline_health.json')
  const trust = useData<Trust>('trust.json')
  if (!allReady([health, trust]) || health.status !== 'ready' || trust.status !== 'ready') return <Status states={[health, trust]} />
  const h = health.data
  const counts = h.tests?.counts ?? {}
  const totalTests = Object.values(counts).reduce((a, b) => a + b, 0)
  const warnings = h.tests?.tests.filter((t) => t.status !== 'pass') ?? []
  const built = h.sources[0]?.built_at_utc
  const bt24 = trust.data.backtest.find((r) => r.horizon === '24h_ahead' && r.fold === 'overall')
  const bt1 = trust.data.backtest.find((r) => r.horizon === '1h_ahead' && r.fold === 'overall')

  return (
    <>
      <div className="page-head">
        <h1>How it works</h1>
        <p>The method behind the site: where the data comes from, how it is checked, and how far to trust the model.</p>
      </div>
      <div className="grid">
        <section className="card span-12" aria-labelledby="h-pipe">
          <h2 id="h-pipe">A daily pipeline from two open APIs to this page</h2>
          <p className="caption">Runs every day on GitHub Actions. Last build {built ? `${ukDateTime(built)} ${ukZone(built)}` : 'unknown'}.</p>
          <ol className="pipeline">
            {STEPS.map((s, i) => (
              <li key={s.title} className="step">
                <span className="step-n num" aria-hidden="true">{i + 1}</span>
                <strong>{s.title}</strong>
                <span className="caption">{s.body}</span>
              </li>
            ))}
          </ol>
          <p className="caption">
            Tools: Python and httpx (ingestion), DuckDB and dbt (warehouse and tests), LightGBM (model), React, TypeScript and ECharts (site).
          </p>
        </section>

        <section className="card span-12" aria-labelledby="h-dq">
          <h2 id="h-dq">
            {totalTests} automated data checks: {counts.pass ?? 0} pass
            {warnings.length ? `, ${warnings.length} warning${warnings.length > 1 ? 's' : ''}` : ''}
            {counts.fail || counts.error ? `, ${(counts.fail ?? 0) + (counts.error ?? 0)} failing` : ''}
          </h2>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <caption className="caption" style={{ textAlign: 'left' }}>Data quality by source</caption>
              <thead>
                <tr>
                  <th scope="col">Source</th><th scope="col">Latest half-hour</th><th scope="col" className="r">Rows</th>
                  <th scope="col" className="r">Duplicates removed</th><th scope="col" className="r">Missing half-hours</th><th scope="col" className="r">Complete</th>
                </tr>
              </thead>
              <tbody>
                {h.sources.map((s) => (
                  <tr key={s.source}>
                    <td>{SOURCE_LABEL[s.source] ?? s.source}</td>
                    <td>{ukDateTime(s.last_period)}</td>
                    <td className="r num">{whole(s.silver_rows)}</td>
                    <td className="r num">{whole(s.duplicates_removed)}</td>
                    <td className="r num">{whole(s.missing_periods)}</td>
                    <td className="r num">{s.completeness_pct.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {warnings.length > 0 && (
            <p style={{ marginTop: 12 }}>
              Warnings: {warnings.map((w) => w.name.replace(/_/g, ' ')).join('; ')}. Gaps come from the source APIs, not from this pipeline:
              they are counted, listed below and never filled with made-up values.
            </p>
          )}
          <details style={{ marginTop: 8 }}>
            <summary className="caption">Most recent days with missing data</summary>
            <table>
              <thead><tr><th scope="col">Date (UTC)</th><th scope="col">Source</th><th scope="col" className="r">Missing half-hours</th></tr></thead>
              <tbody>
                {h.gap_days.slice(0, 20).map((g) => (
                  <tr key={`${g.source}-${g.utc_date}`}><td>{g.utc_date}</td><td>{SOURCE_LABEL[g.source] ?? g.source}</td><td className="r num">{g.missing_half_hours}</td></tr>
                ))}
              </tbody>
            </table>
          </details>
        </section>

        <section className="card span-12" aria-labelledby="h-card">
          <h2 id="h-card">Model card: forecast error correction</h2>
          <dl className="model-card">
            <dt>What it does</dt>
            <dd>Predicts how far NESO's national forecast will miss (actual minus forecast) and adds that to the forecast.</dd>
            <dt>Approach</dt>
            <dd>LightGBM gradient-boosted trees on the forecast error. Two versions: using information up to 1 hour and up to 24 hours before each half-hour.</dd>
            <dt>Features</dt>
            <dd>The official forecast; recent errors (latest, 6-hour and 24-hour averages, same time yesterday); change in forecast; recent PV_Live solar output; UK hour, weekday and month. All shifted so nothing from after the cut-off is used (unit-tested).</dd>
            <dt>Evaluation</dt>
            <dd>Rolling-origin backtest: for every month since January 2024, train on all earlier data only, then test on that month.</dd>
            <dt>Results</dt>
            <dd>
              {bt24 && <>24 hours ahead: MAE {bt24.mae_model.toFixed(2)} vs official {bt24.mae_official.toFixed(2)}. </>}
              {bt1 && <>1 hour ahead: MAE {bt1.mae_model.toFixed(2)} vs official {bt1.mae_official.toFixed(2)}. </>}
              gCO₂/kWh. See the <a href="#/trust">Trust page</a>.
            </dd>
            <dt>Limitations</dt>
            <dd>
              History holds only NESO's final forecast, which may be issued close to the half-hour, so the comparison shows improvement on the
              published forecast, not on a genuine day-ahead forecast. It assumes recent actuals are available in time, which may not hold in
              real time. National only. Not used for the regional figures elsewhere on this site.
            </dd>
            <dt>When not to trust it</dt>
            <dd>Unusual events (outages, extreme weather, holidays unlike past data), and whenever the latest actuals are missing or delayed.</dd>
          </dl>
        </section>

        <section className="card span-6" aria-labelledby="h-links">
          <h2 id="h-links">Read the code and the reasoning</h2>
          <ul>
            <li><a href={REPO}>Source code on GitHub</a></li>
            <li><a href={`${REPO}/blob/main/docs/DECISIONS.md`}>DECISIONS.md</a>: every non-obvious choice and why</li>
            <li><a href={`${REPO}/blob/main/docs/BUILD_LOG.md`}>BUILD_LOG.md</a>: what was built, what broke and how it was fixed</li>
          </ul>
        </section>

        <section className="card span-6" aria-labelledby="h-claude">
          <h2 id="h-claude">How this was built with Claude Code</h2>
          <p>
            The code was written by Claude Code (an AI coding assistant) working from a written spec, in five phases. Each phase ended with
            acceptance checks run and recorded as evidence in the build log.
          </p>
          <p>
            The human (Samuel) wrote the spec and the acceptance criteria, made the product decisions, and reviewed each phase: the data
            choices, the model's honesty and the wording. Mistakes the AI made and fixed are recorded in the build log, not hidden.
          </p>
        </section>
      </div>
    </>
  )
}
