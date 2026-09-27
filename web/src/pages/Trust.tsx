import { useMemo, useState } from 'react'
import Chart, { axisStyle } from '../components/Chart'
import Status, { allReady } from '../components/Status'
import { useData, type BacktestRow, type Trust as TrustData } from '../lib/data'
import { ukDateTime } from '../lib/format'
import { cssVar } from '../lib/palette'
import { useTheme } from '../lib/theme'

const HORIZON_LABEL: Record<string, string> = { '1h_ahead': '1 hour ahead', '24h_ahead': '24 hours ahead' }

const FEATURE_LABEL: Record<string, string> = {
  forecast: 'Official forecast for the half-hour',
  err_lag: 'Latest known forecast error',
  err_lag_mean_6h: 'Average error, previous 6 hours',
  err_lag_mean_24h: 'Average error, previous 24 hours',
  err_same_slot_prev_day: 'Error at the same time yesterday',
  forecast_change: 'Change in forecast since issue time',
  solar_lag_mw: 'Latest known solar output',
  solar_same_slot_prev_day_mw: 'Solar output same time yesterday',
  local_hour: 'Time of day',
  day_of_week: 'Day of week',
  month: 'Month',
}

function pct(a: number, b: number): number {
  return Math.round((100 * (a - b)) / a)
}

export default function Trust() {
  const trust = useData<TrustData>('trust.json')
  const theme = useTheme()
  const [horizon, setHorizon] = useState<'24h_ahead' | '1h_ahead'>('24h_ahead')

  const d = trust.status === 'ready' ? trust.data : null
  const by = (g: string) => d?.accuracy.filter((r) => r.grouping === g) ?? []
  const overall = by('overall')[0]
  const months = by('month')
  const hours = by('local_hour')
  const wind = by('wind_regime').filter((r) => r.group_key !== 'unknown')
  const folds: BacktestRow[] = d?.backtest.filter((r) => r.horizon === horizon && r.fold !== 'overall') ?? []
  const bt = d?.backtest.find((r) => r.horizon === horizon && r.fold === 'overall')

  const monthOpt = useMemo(() => {
    const ax = axisStyle()
    return {
      grid: { left: 48, right: 16, top: 24, bottom: 40 },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${v} gCO₂/kWh` },
      xAxis: { type: 'category', data: months.map((m) => m.group_key), ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', name: 'MAE, gCO₂/kWh', min: 0, ...ax },
      series: [{ type: 'line', name: 'Mean absolute error', data: months.map((m) => m.mae), showSymbol: false, lineStyle: { color: cssVar('--text'), width: 2 }, itemStyle: { color: cssVar('--text') } }],
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, theme])

  const hourOpt = useMemo(() => {
    const ax = axisStyle()
    return {
      grid: { left: 48, right: 16, top: 24, bottom: 40 },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${v} gCO₂/kWh` },
      xAxis: { type: 'category', name: 'UK hour', nameLocation: 'middle', nameGap: 26, data: hours.map((h) => `${h.group_key}:00`), ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', name: 'MAE, gCO₂/kWh', min: 0, ...ax },
      series: [{ type: 'bar', name: 'Mean absolute error', data: hours.map((h) => h.mae), itemStyle: { color: cssVar('--accent'), borderRadius: [3, 3, 0, 0] } }],
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, theme])

  const backtestOpt = useMemo(() => {
    const ax = axisStyle()
    return {
      grid: { left: 48, right: 16, top: 40, bottom: 40 },
      legend: { top: 0, textStyle: { color: cssVar('--text-muted') } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${v.toFixed(1)} gCO₂/kWh` },
      xAxis: { type: 'category', data: folds.map((f) => f.fold), ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', name: 'MAE, gCO₂/kWh', min: 0, ...ax },
      series: [
        { type: 'line', name: 'Official forecast', data: folds.map((f) => f.mae_official), showSymbol: false, lineStyle: { color: '#8C96A3', width: 2 }, itemStyle: { color: '#8C96A3' } },
        { type: 'line', name: 'Our model', data: folds.map((f) => f.mae_model), showSymbol: false, lineStyle: { color: cssVar('--accent'), width: 2 }, itemStyle: { color: cssVar('--accent') } },
      ],
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, horizon, theme])

  if (!allReady([trust]) || !d || !overall || !bt) return <Status states={[trust]} />

  const worstMonth = [...months].sort((a, b) => b.mae - a.mae)[0]
  const bestMonth = [...months].sort((a, b) => a.mae - b.mae)[0]
  const worstHour = [...hours].sort((a, b) => b.mae - a.mae)[0]
  const bestHour = [...hours].sort((a, b) => a.mae - b.mae)[0]
  const windSorted = [...wind].sort((a, b) => b.mae - a.mae)
  const monthsWon = folds.filter((f) => f.mae_model < f.mae_official).length
  const beats = bt.mae_model < bt.mae_official
  const topFeatures = d.features.filter((f) => f.horizon === horizon).slice(0, 5)

  return (
    <>
      <div className="page-head">
        <h1>Can you trust the forecast?</h1>
        <p>How accurate NESO's national carbon intensity forecast has been, and whether a simple model can do better.</p>
      </div>
      <div className="grid">
        <section className="card span-12" aria-labelledby="t-head">
          <h2 id="t-head">
            On average the official forecast is out by {overall.mae.toFixed(1)} gCO₂/kWh ({overall.mae_pct_of_mean}% of the typical value)
          </h2>
          <p>
            Measured over {overall.n.toLocaleString('en-GB')} half-hours since January 2023. The bias is{' '}
            {Math.abs(overall.bias) < 1 ? 'close to zero' : overall.bias > 0 ? `+${overall.bias} (it tends to run low)` : `${overall.bias} (it tends to run high)`},
            so errors go both ways rather than always one way.
          </p>
          <p className="caption">
            Mean absolute error (MAE): the average size of the gap between forecast and measured value, ignoring its direction. National only:
            NESO publishes measured actuals for Great Britain as a whole, not for regions.
          </p>
        </section>

        <section className="card span-12" aria-labelledby="t-vintage">
          <h2 id="t-vintage">An important caveat: which forecast is being tested?</h2>
          <p>
            For past half-hours the API keeps only the <strong>final</strong> forecast, which may have been updated shortly before the
            half-hour began. So the figures on this page are "final forecast vs actual". They flatter the forecast compared with what
            you would have seen a day ahead.
          </p>
          <p>
            To measure true day-ahead accuracy, this project saves a copy of the 48-hour forecast every day.{' '}
            <strong>Snapshots collected so far: {d.snapshot_days.days} day{d.snapshot_days.days === 1 ? '' : 's'}</strong>
            {d.snapshot_days.first ? ` (since ${ukDateTime(d.snapshot_days.first)})` : ''}.
            {d.snapshot_accuracy.length === 0
              ? ' None of the snapshotted half-hours has a measured actual yet, so day-ahead accuracy will appear here as they come in.'
              : ''}
          </p>
          {d.snapshot_accuracy.length > 0 && (
            <table>
              <caption className="caption" style={{ textAlign: 'left' }}>Accuracy of saved forecasts, by how far ahead they were made</caption>
              <thead><tr><th scope="col">Lead time</th><th scope="col" className="r">Half-hours</th><th scope="col" className="r">MAE</th><th scope="col" className="r">Bias</th></tr></thead>
              <tbody>
                {d.snapshot_accuracy.map((r) => (
                  <tr key={r.lead_bucket}><td>{r.lead_bucket}</td><td className="r num">{r.n}</td><td className="r num">{r.mae}</td><td className="r num">{r.bias}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="card span-12" aria-labelledby="t-month">
          <h2 id="t-month">Monthly error has ranged from {bestMonth.mae.toFixed(1)} ({bestMonth.group_key}) to {worstMonth.mae.toFixed(1)} ({worstMonth.group_key})</h2>
          <p className="caption">Mean absolute error of the official final forecast by month, gCO₂/kWh</p>
          <Chart option={monthOpt} label={`Monthly forecast error. Lowest ${bestMonth.mae} in ${bestMonth.group_key}, highest ${worstMonth.mae} in ${worstMonth.group_key}.`} />
        </section>

        <section className="card span-7" aria-labelledby="t-hour">
          <h2 id="t-hour">Least accurate around {worstHour.group_key}:00, most accurate around {bestHour.group_key}:00</h2>
          <p className="caption">Mean absolute error by UK hour of day, gCO₂/kWh</p>
          <Chart option={hourOpt} label={`Forecast error by hour. Worst at ${worstHour.group_key}:00 (${worstHour.mae}), best at ${bestHour.group_key}:00 (${bestHour.mae}).`} />
        </section>

        <section className="card span-5" aria-labelledby="t-wind">
          <h2 id="t-wind">Error is largest in {windSorted[0]?.group_key.split(' (')[0]} periods</h2>
          <p className="caption">By wind's share of generation. "% of typical" is MAE relative to average intensity in those periods.</p>
          <table>
            <thead><tr><th scope="col">Conditions</th><th scope="col" className="r">MAE</th><th scope="col" className="r">% of typical</th><th scope="col" className="r">Half-hours</th></tr></thead>
            <tbody>
              {wind.map((w) => (
                <tr key={w.group_key}>
                  <td>{w.group_key}</td>
                  <td className="r num">{w.mae.toFixed(1)}</td>
                  <td className="r num">{w.mae_pct_of_mean}%</td>
                  <td className="r num">{w.n.toLocaleString('en-GB')}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="caption" style={{ marginTop: 8 }}>
            In windy periods intensity is low, so a similar absolute error is a bigger share of the value.
          </p>
        </section>

        <section className="card span-12" aria-labelledby="t-model">
          <h2 id="t-model">
            {beats
              ? `Our model cut the error by ${pct(bt.mae_official, bt.mae_model)}% (${HORIZON_LABEL[horizon]}), beating the official forecast in ${monthsWon} of ${folds.length} months`
              : `Our model did not beat the official forecast (${HORIZON_LABEL[horizon]})`}
          </h2>
          <div className="chips" role="group" aria-label="Forecast horizon" style={{ marginBottom: 12 }}>
            {(['24h_ahead', '1h_ahead'] as const).map((h) => (
              <button key={h} type="button" className="chip" aria-pressed={h === horizon} onClick={() => setHorizon(h)}>
                {HORIZON_LABEL[h]}
              </button>
            ))}
          </div>
          <p className="caption">
            Monthly MAE in a rolling backtest: for each month, the model is trained only on earlier data, then tested on that month.
          </p>
          <Chart option={backtestOpt} label={`Backtest: official MAE ${bt.mae_official.toFixed(2)}, model MAE ${bt.mae_model.toFixed(2)}.`} />
          <table style={{ marginTop: 12 }}>
            <caption className="caption" style={{ textAlign: 'left' }}>
              Whole backtest, {bt.n.toLocaleString('en-GB')} half-hours from {folds[0]?.fold} to {folds[folds.length - 1]?.fold}
            </caption>
            <thead><tr><th scope="col">Method</th><th scope="col" className="r">MAE, gCO₂/kWh</th><th scope="col" className="r">Bias</th></tr></thead>
            <tbody>
              <tr><td>Official NESO forecast (baseline)</td><td className="r num">{bt.mae_official.toFixed(2)}</td><td className="r num">{bt.bias_official.toFixed(2)}</td></tr>
              <tr><td>Official + latest known error (simple baseline)</td><td className="r num">{bt.mae_recent_error.toFixed(2)}</td><td className="r num">–</td></tr>
              <tr><td><strong>Our error-correction model</strong></td><td className="r num"><strong>{bt.mae_model.toFixed(2)}</strong></td><td className="r num">{bt.bias_model.toFixed(2)}</td></tr>
            </tbody>
          </table>
          <h3 style={{ marginTop: 16 }}>What the model leans on most</h3>
          <ol>
            {topFeatures.map((f) => (
              <li key={f.feature}>{FEATURE_LABEL[f.feature] ?? f.feature} <span className="muted num">({Math.round(f.importance_share * 100)}%)</span></li>
            ))}
          </ol>
          <p>
            <strong>Read this with care.</strong> The model corrects the <em>final</em> forecast using only information available{' '}
            {horizon === '24h_ahead' ? '24 hours' : '1 hour'} before each half-hour. Because the final forecast itself may be issued later than that,
            this shows the model improves on the published forecast, not that it would beat a genuine day-ahead forecast. The daily snapshots
            will test that properly. Full details are in the model card on the <a href="#/how">How it works</a> page.
          </p>
        </section>
      </div>
    </>
  )
}
