import { useMemo, useState } from 'react'
import Chart, { axisStyle } from '../components/Chart'
import RegionSelect from '../components/RegionSelect'
import Status, { allReady } from '../components/Status'
import { bestWindow, co2SavedGrams, type Point } from '../lib/bestWindow'
import { useData, type Region, type Region48h } from '../lib/data'
import { grams, ukDateTime, ukDayTime, ukTime, ukZone } from '../lib/format'
import { bandColour, bandLabel, cssVar } from '../lib/palette'
import { useRegion } from '../lib/region'
import { useTheme } from '../lib/theme'

interface Task {
  id: string
  label: string
  hours: number
  /** Energy assumption, stated on the page. */
  kwh: number
  note: string
}

// Stated assumptions: typical figures, rounded, not measurements.
const TASKS: Task[] = [
  { id: 'ev', label: 'EV charge', hours: 4, kwh: 28, note: '7 kW home charger for 4 hours' },
  { id: 'wash', label: 'Washing machine', hours: 2, kwh: 1, note: 'a 40°C cycle, about 1 kWh' },
  { id: 'dish', label: 'Dishwasher', hours: 2, kwh: 1.2, note: 'an eco cycle, about 1.2 kWh' },
  { id: 'custom', label: 'Custom', hours: 3, kwh: 5, note: 'your own figures' },
]

const nowMs = () => Date.now()

export default function Plan() {
  const regions = useData<Region[]>('regions.json')
  const fc = useData<Region48h>('region_48h.json')
  const selected = useRegion()
  const theme = useTheme()
  const [taskId, setTaskId] = useState('ev')
  const [customHours, setCustomHours] = useState(3)
  const [customKwh, setCustomKwh] = useState(5)

  const task = TASKS.find((t) => t.id === taskId)!
  const hours = task.id === 'custom' ? customHours : task.hours
  const kwh = task.id === 'custom' ? customKwh : task.kwh
  const slots = Math.max(1, Math.round(hours * 2))

  const series = useMemo(
    () => (fc.status === 'ready' ? fc.data.regions[String(selected)] ?? [] : []),
    [fc, selected],
  )
  const points: Point[] = useMemo(() => series.map(([t, v]) => ({ t: Date.parse(t), v })), [series])
  const regionName = regions.status === 'ready' ? regions.data.find((r) => r.region_id === selected)?.short_name ?? '' : ''
  // Before the first slot of the forecast, "now" is the first forecast slot.
  const fromT = Math.max(nowMs(), points[0]?.t ?? 0)
  const result = useMemo(() => bestWindow(points, slots, fromT), [points, slots, fromT])

  const option = useMemo(() => {
    const ax = axisStyle()
    const accent = cssVar('--accent')
    const text = cssVar('--text')
    return {
      grid: { left: 48, right: 16, top: 36, bottom: 40 },
      tooltip: {
        trigger: 'axis',
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0].dataIndex
          const [t, v, band] = series[i]
          return `${ukDayTime(t)} ${ukZone(t)}<br/><b>${v} gCO₂/kWh</b> · ${bandLabel(band)}`
        },
      },
      xAxis: {
        type: 'time',
        ...ax,
        splitLine: { show: false },
        axisLabel: { ...ax.axisLabel, formatter: (v: number) => ukDayTime(v), hideOverlap: true },
      },
      yAxis: { type: 'value', name: 'gCO₂/kWh', min: 0, ...ax },
      series: [
        {
          type: 'line',
          showSymbol: false,
          step: 'start',
          lineStyle: { width: 2, color: text },
          itemStyle: { color: text },
          data: points.map((p) => [p.t, p.v]),
          markArea: result
            ? {
                silent: true,
                itemStyle: { color: accent, opacity: 0.18 },
                label: { show: true, position: 'insideTop', color: accent, formatter: 'Cleanest' },
                data: [[{ xAxis: result.start }, { xAxis: result.end }]],
              }
            : undefined,
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: cssVar('--text-muted'), type: 'dashed' },
            label: { formatter: 'Now', position: 'insideEndTop', color: cssVar('--text-muted') },
            data: [{ xAxis: nowMs() }],
          },
        },
      ],
    }
    // theme is listed so colours refresh when it changes
  }, [points, result, series, theme])

  if (!allReady([regions, fc]) || regions.status !== 'ready' || fc.status !== 'ready') {
    return <Status states={[regions, fc]} />
  }

  const saved = result ? co2SavedGrams(result, kwh) : 0
  const title = result
    ? `Cleanest ${hours}-hour window: ${ukDayTime(result.start)}–${ukTime(result.end)}`
    : 'Not enough forecast for this task'

  return (
    <>
      <div className="page-head">
        <h1>When should I run it?</h1>
        <p>Find the cleanest time in the next 48 hours for a job that uses electricity.</p>
      </div>
      <div className="grid">
        <section className="card span-12" aria-labelledby="finder-h">
          <h2 id="finder-h">Best-window finder</h2>
          <div className="controls">
            <RegionSelect regions={regions.data} />
            <div>
              <span id="task-label" className="caption" style={{ display: 'block', marginBottom: 4 }}>Task</span>
              <div className="chips" role="group" aria-labelledby="task-label">
                {TASKS.map((t) => (
                  <button key={t.id} type="button" className="chip" aria-pressed={t.id === taskId} onClick={() => setTaskId(t.id)}>
                    {t.label}{t.id !== 'custom' ? ` · ${t.hours}h` : ''}
                  </button>
                ))}
              </div>
            </div>
            {task.id === 'custom' && (
              <>
                <div>
                  <label htmlFor="hours">Duration (hours)</label>
                  <input id="hours" type="number" min={0.5} max={24} step={0.5} value={customHours}
                    onChange={(e) => setCustomHours(Math.min(24, Math.max(0.5, Number(e.target.value) || 0.5)))} />
                </div>
                <div>
                  <label htmlFor="kwh">Energy used (kWh)</label>
                  <input id="kwh" type="number" min={0.1} max={200} step={0.1} value={customKwh}
                    onChange={(e) => setCustomKwh(Math.min(200, Math.max(0.1, Number(e.target.value) || 0.1)))} />
                </div>
              </>
            )}
          </div>

          <div className="result" aria-live="polite">
            {result ? (
              <>
                <div className="caption">Best start time in {regionName} ({ukZone(result.start)})</div>
                <div className="when">{ukDayTime(result.start)} to {ukTime(result.end)}</div>
                <div className="stat-row">
                  <div className="stat"><div className="v num">{Math.round(result.avg)} gCO₂/kWh</div><div className="l">average in that window</div></div>
                  <div className="stat"><div className="v num">{Math.round(result.nowAvg)} gCO₂/kWh</div><div className="l">if you start now</div></div>
                  <div className="stat">
                    <div className="v num">{saved > 0.5 ? grams(saved) : 'No saving'}</div>
                    <div className="l">CO₂ saved vs starting now</div>
                  </div>
                </div>
                <p className="caption" style={{ marginTop: 8 }}>
                  Assumes {kwh} kWh ({task.note}), spread evenly over {hours} hours. Uses the NESO regional forecast
                  captured {ukDateTime(fc.data.captured_at)}.
                </p>
              </>
            ) : (
              <p>The task is longer than the forecast that remains. Try a shorter duration.</p>
            )}
          </div>
        </section>

        <section className="card span-12" aria-labelledby="fc-h">
          <h2 id="fc-h">{title}</h2>
          <p className="caption">
            Forecast carbon intensity for {regionName}, next 48 hours, gCO₂/kWh, UK time. Shaded: the cleanest window for this task.
          </p>
          <Chart option={option} label={`48-hour forecast for ${regionName}. ${title}.`} />
          <details style={{ marginTop: 8 }}>
            <summary className="caption">Show the forecast as a table</summary>
            <table>
              <thead><tr><th scope="col">Time ({ukZone()})</th><th scope="col" className="r">gCO₂/kWh</th><th scope="col">Band</th></tr></thead>
              <tbody>
                {series.map(([t, v, b]) => (
                  <tr key={t}>
                    <td>{ukDayTime(t)}</td>
                    <td className="r num">{v}</td>
                    <td><span className="band-dot" style={{ background: bandColour(b), marginRight: 6 }} aria-hidden="true" />{bandLabel(b)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </section>
      </div>
    </>
  )
}
