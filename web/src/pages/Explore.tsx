import { useMemo, useState } from 'react'
import Chart, { axisStyle } from '../components/Chart'
import Status, { allReady } from '../components/Status'
import { useData, type Explore as ExploreData, type InsightRow, type Region } from '../lib/data'
import { ukDateTime, whole } from '../lib/format'
import { BAND_COLOURS, cssVar, FUEL_COLOURS } from '../lib/palette'
import { useTheme } from '../lib/theme'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const hh = (h: number) => `${String(h).padStart(2, '0')}:00`

/** Turn the computed numbers into the three insight sentences. */
function insightText(r: InsightRow, name: (id: number) => string): { title: string; body: string } {
  if (r.card === 'cleanest_hour') {
    const worse = Math.round((100 * (r.value_4! - r.value_2)) / r.value_2)
    return {
      title: `Cleanest around ${hh(r.value_1)}, dirtiest around ${hh(r.value_3!)}`,
      body: `Over the past year GB electricity averaged ${whole(r.value_2)} gCO₂/kWh at ${hh(r.value_1)} and ${whole(r.value_4!)} at ${hh(r.value_3!)}, ${worse}% more carbon per unit.`,
    }
  }
  if (r.card === 'year_on_year') {
    const change = Math.round((100 * (r.value_1 - r.value_2)) / r.value_2)
    return {
      title: change < 0 ? `The grid is ${-change}% cleaner than a year earlier` : `The grid is ${change}% dirtier than a year earlier`,
      body: `Average measured intensity over the last 12 months was ${whole(r.value_1)} gCO₂/kWh, against ${whole(r.value_2)} in the 12 months before.`,
    }
  }
  const ratio = r.value_4! / Math.max(r.value_2, 0.1)
  return {
    title: `${name(r.value_3!)} is far dirtier than ${name(r.value_1)}`,
    body: `Over the past year ${name(r.value_1)} averaged ${whole(r.value_2)} gCO₂/kWh and ${name(r.value_3!)} ${whole(r.value_4!)}${ratio >= 2 ? `, about ${whole(ratio)} times as much` : ''}. These are regional forecasts; no regional actuals exist.`,
  }
}

export default function Explore() {
  const ex = useData<ExploreData>('explore.json')
  const regions = useData<Region[]>('regions.json')
  const theme = useTheme()
  const [windowDays, setWindowDays] = useState(30)
  const d = ex.status === 'ready' ? ex.data : null

  const heatOpt = useMemo(() => {
    if (!d) return {}
    const ax = axisStyle()
    const values = d.heatmap.map((c) => c.avg_actual_gco2_kwh)
    return {
      grid: { left: 48, right: 16, top: 16, bottom: 72 },
      tooltip: {
        formatter: (p: { value: [number, number, number] }) =>
          `${MONTHS[p.value[1]]}, ${hh(p.value[0])} UK time<br/><b>${p.value[2]} gCO₂/kWh</b> (average)`,
      },
      xAxis: { type: 'category', data: Array.from({ length: 24 }, (_, i) => hh(i)), name: 'UK hour', nameLocation: 'middle', nameGap: 28, ...ax, splitLine: { show: false } },
      yAxis: { type: 'category', data: MONTHS, inverse: true, ...ax, splitLine: { show: false } },
      visualMap: {
        min: Math.floor(Math.min(...values)),
        max: Math.ceil(Math.max(...values)),
        calculable: false,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        itemWidth: 12,
        text: ['dirtier', 'cleaner'],
        textStyle: { color: cssVar('--text-muted') },
        inRange: { color: [BAND_COLOURS['very low'], BAND_COLOURS.low, BAND_COLOURS.moderate, BAND_COLOURS.high, BAND_COLOURS['very high']] },
      },
      series: [{ type: 'heatmap', data: d.heatmap.map((c) => [c.local_hour, c.local_month - 1, c.avg_actual_gco2_kwh]) }],
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, theme])

  const solarOpt = useMemo(() => {
    if (!d) return {}
    const ax = axisStyle()
    const slots = d.solar.filter((s) => s.season === 'summer').map((s) => s.local_time)
    const pick = (season: string, key: 'avg_solar_mw' | 'avg_actual_gco2_kwh') =>
      d.solar.filter((s) => s.season === season).map((s) => (key === 'avg_solar_mw' ? Math.round(s[key] / 100) / 10 : s[key]))
    return {
      grid: { left: 48, right: 56, top: 48, bottom: 40 },
      legend: { top: 0, textStyle: { color: cssVar('--text-muted') } },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: slots, ...ax, splitLine: { show: false }, axisLabel: { ...ax.axisLabel, interval: 5 } },
      yAxis: [
        { type: 'value', name: 'Solar, GW', min: 0, ...ax },
        { type: 'value', name: 'gCO₂/kWh', min: 0, ...ax, splitLine: { show: false } },
      ],
      series: [
        { type: 'line', name: 'Solar, summer (GW)', data: pick('summer', 'avg_solar_mw'), showSymbol: false, areaStyle: { opacity: 0.15 }, lineStyle: { color: FUEL_COLOURS.solar, width: 2 }, itemStyle: { color: FUEL_COLOURS.solar } },
        { type: 'line', name: 'Solar, winter (GW)', data: pick('winter', 'avg_solar_mw'), showSymbol: false, lineStyle: { color: FUEL_COLOURS.solar, width: 2, type: 'dashed' }, itemStyle: { color: FUEL_COLOURS.solar } },
        { type: 'line', name: 'Intensity, summer', yAxisIndex: 1, data: pick('summer', 'avg_actual_gco2_kwh'), showSymbol: false, lineStyle: { color: cssVar('--text'), width: 2 }, itemStyle: { color: cssVar('--text') } },
        { type: 'line', name: 'Intensity, winter', yAxisIndex: 1, data: pick('winter', 'avg_actual_gco2_kwh'), showSymbol: false, lineStyle: { color: cssVar('--text'), width: 2, type: 'dashed' }, itemStyle: { color: cssVar('--text') } },
      ],
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, theme])

  if (!allReady([ex, regions]) || !d || regions.status !== 'ready') return <Status states={[ex, regions]} />

  const name = (id: number) => regions.data.find((r) => r.region_id === id)?.short_name ?? `Region ${id}`
  const heatMin = d.heatmap.reduce((a, b) => (b.avg_actual_gco2_kwh < a.avg_actual_gco2_kwh ? b : a))
  const summer = d.solar.filter((s) => s.season === 'summer')
  const summerPeak = summer.reduce((a, b) => (b.avg_solar_mw > a.avg_solar_mw ? b : a))
  const summerNight = summer.find((s) => s.local_time === '03:00')!
  const summerMidday = summer.find((s) => s.local_time === summerPeak.local_time)!
  const league = d.league.filter((l) => l.window_days === windowDays)
  const asOf = d.insights[0]?.as_of_utc

  return (
    <>
      <div className="page-head">
        <h1>Explore</h1>
        <p>Patterns in GB grid data since January 2023: when, where and why electricity is cleaner.</p>
      </div>
      <div className="grid">
        {d.insights.map((r) => {
          const t = insightText(r, name)
          return (
            <section key={r.card} className="card span-4" aria-label={t.title}>
              <h2>{t.title}</h2>
              <p className="muted">{t.body}</p>
            </section>
          )
        })}
        <p className="caption span-12">Figures computed from the data up to {asOf ? ukDateTime(asOf) : 'the latest update'}, refreshed daily.</p>

        <section className="card span-12" aria-labelledby="e-heat">
          <h2 id="e-heat">Cleanest on average: {MONTHS[heatMin.local_month - 1]} around {hh(heatMin.local_hour)} ({whole(heatMin.avg_actual_gco2_kwh)} gCO₂/kWh)</h2>
          <p className="caption">Average measured national carbon intensity by UK hour and month, 2023 to date, gCO₂/kWh</p>
          <Chart option={heatOpt} label="Heatmap of average carbon intensity by hour of day and month" className="chart" />
        </section>

        <section className="card span-12" aria-labelledby="e-solar">
          <h2 id="e-solar">
            On summer days solar peaks at {(summerPeak.avg_solar_mw / 1000).toFixed(1)} GW around {summerPeak.local_time}, when intensity is{' '}
            {whole(summerMidday.avg_actual_gco2_kwh)} against {whole(summerNight.avg_actual_gco2_kwh)} at 03:00
          </h2>
          <p className="caption">
            Average national solar output (PV_Live estimate, GW, left) and measured carbon intensity (gCO₂/kWh, right) by UK time of day.
            Summer is June to August; winter is December to February.
          </p>
          <Chart option={solarOpt} label="Solar output and carbon intensity through the day, summer and winter" />
          <p style={{ marginTop: 8 }}>
            <strong>The hidden solar story.</strong> Most GB solar panels sit on roofs and small sites connected to local networks, not the
            national grid, so the grid operator cannot measure them directly. Sheffield Solar's PV_Live estimates their output. To the grid, this
            solar looks like people using less electricity at midday. Record so far: <strong>{(d.solar_peak.mw / 1000).toFixed(1)} GW</strong>{' '}
            at {ukDateTime(d.solar_peak.at_utc)}.
          </p>
        </section>

        <section className="card span-12" aria-labelledby="e-league">
          <h2 id="e-league">
            {league[0]?.short_name} was cleanest and {league[league.length - 1]?.short_name} dirtiest over the last {windowDays} days
          </h2>
          <div className="chips" role="group" aria-label="Period" style={{ marginBottom: 12 }}>
            {[30, 365].map((w) => (
              <button key={w} type="button" className="chip" aria-pressed={w === windowDays} onClick={() => setWindowDays(w)}>
                Last {w} days
              </button>
            ))}
          </div>
          <table>
            <caption className="caption" style={{ textAlign: 'left' }}>Average forecast carbon intensity by region, cleanest first</caption>
            <thead><tr><th scope="col" className="r">Rank</th><th scope="col">Region</th><th scope="col" className="r">Average gCO₂/kWh</th><th scope="col" className="r">Time at low or very low</th></tr></thead>
            <tbody>
              {league.map((l) => (
                <tr key={l.region_id}>
                  <td className="r num">{l.rank}</td>
                  <td>{l.short_name}</td>
                  <td className="r num">{whole(l.avg_gco2_kwh)}</td>
                  <td className="r num">{Math.round(l.pct_low_or_very_low)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </>
  )
}
