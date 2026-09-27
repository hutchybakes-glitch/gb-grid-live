import { useMemo } from 'react'
import Chart from '../components/Chart'
import RegionMap from '../components/RegionMap'
import RegionSelect from '../components/RegionSelect'
import Status, { allReady } from '../components/Status'
import { useData, type Region, type RegionNow } from '../lib/data'
import { ukTime, ukZone } from '../lib/format'
import { BANDS, bandColour, bandLabel, FUEL_COLOURS } from '../lib/palette'
import { setRegion, useRegion } from '../lib/region'
import { nowSentence } from '../lib/sentence'

export default function Now() {
  const regions = useData<Region[]>('regions.json')
  const now = useData<RegionNow[]>('region_now.json')
  const selected = useRegion()

  const current = now.status === 'ready' ? now.data.find((r) => r.region_id === selected) : undefined
  const mix = useMemo(
    () => (current?.generation_mix ?? []).filter((m) => m.perc > 0).sort((a, b) => b.perc - a.perc),
    [current],
  )

  const donut = useMemo(
    () => ({
      tooltip: { trigger: 'item', formatter: (p: { name: string; value: number }) => `${p.name}: ${p.value}%` },
      series: [
        {
          type: 'pie',
          radius: ['52%', '78%'],
          avoidLabelOverlap: true,
          label: { formatter: '{b}\n{c}%', color: 'inherit', fontSize: 12 },
          data: mix.map((m) => ({ name: m.fuel, value: m.perc, itemStyle: { color: FUEL_COLOURS[m.fuel] ?? '#B0B0B0' } })),
        },
      ],
    }),
    [mix],
  )

  if (!allReady([regions, now]) || regions.status !== 'ready' || now.status !== 'ready') {
    return <Status states={[regions, now]} />
  }

  const dnoRegions = now.data.filter((r) => r.region_id <= 14)
  const mixText = mix.map((m) => `${m.fuel} ${m.perc}%`).join(', ')

  return (
    <>
      <div className="page-head">
        <h1>How clean is the grid right now?</h1>
        <p>Carbon intensity (grams of CO₂ emitted per kilowatt-hour of electricity) where you live, this half-hour.</p>
      </div>

      <div className="grid">
        <section className="card span-7" aria-labelledby="now-h">
          <div className="controls"><RegionSelect regions={regions.data} /></div>
          {current ? (
            <>
              <h2 id="now-h" className="muted" style={{ fontWeight: 500, fontSize: 15 }}>
                {current.short_name}, {ukTime(current.period_start_utc)}–{ukTime(Date.parse(current.period_start_utc) + 1800000)} {ukZone(current.period_start_utc)}
              </h2>
              <div className="headline">
                <span className="big num">{current.forecast_gco2_kwh}</span>
                <span className="unit">gCO₂/kWh</span>
                <span className="band-pill">
                  <span className="band-dot" style={{ background: bandColour(current.intensity_index) }} aria-hidden="true" />
                  {bandLabel(current.intensity_index)}
                </span>
              </div>
              <p className="sentence">{nowSentence(current)}</p>
              <p className="caption">
                Regional figures are NESO forecasts for this half-hour; measured actuals exist only for GB as a whole.
              </p>
            </>
          ) : (
            <p>No current forecast for this region.</p>
          )}
        </section>

        <section className="card span-5" aria-labelledby="mix-h">
          <h2 id="mix-h">
            {mix.length ? `${mix[0].fuel.charAt(0).toUpperCase() + mix[0].fuel.slice(1)} is the biggest source right now` : 'Generation mix'}
          </h2>
          <p className="caption">Share of electricity by fuel, {current?.short_name}, this half-hour (%)</p>
          <Chart option={donut} label={`Generation mix: ${mixText}`} className="chart chart-sm" />
        </section>

        <section className="card span-12" aria-labelledby="map-h">
          <h2 id="map-h">
            {(() => {
              const cleanest = [...dnoRegions].sort((a, b) => a.forecast_gco2_kwh - b.forecast_gco2_kwh)[0]
              return `${cleanest.short_name} is the cleanest region right now`
            })()}
          </h2>
          <p className="caption">Forecast carbon intensity by region, gCO₂/kWh. Select a region to see its details.</p>
          <div className="grid" style={{ alignItems: 'center' }}>
            <div className="span-6">
              <RegionMap regions={dnoRegions} selected={selected} onSelect={setRegion} />
            </div>
            <div className="span-6">
              <div className="legend" aria-label="Colour key">
                {BANDS.map((b) => (
                  <span key={b}><span className="band-dot" style={{ background: bandColour(b) }} aria-hidden="true" />{bandLabel(b)}</span>
                ))}
              </div>
              <table style={{ marginTop: 12 }}>
                <caption className="caption" style={{ textAlign: 'left' }}>Regions, cleanest first</caption>
                <thead><tr><th scope="col">Region</th><th scope="col" className="r">gCO₂/kWh</th><th scope="col">Band</th></tr></thead>
                <tbody>
                  {[...dnoRegions].sort((a, b) => a.forecast_gco2_kwh - b.forecast_gco2_kwh).map((r) => (
                    <tr key={r.region_id} aria-current={r.region_id === selected ? 'true' : undefined}>
                      <td>
                        <button className="icon-btn" style={{ border: 0, padding: 0 }} type="button" onClick={() => setRegion(r.region_id)}>
                          {r.short_name}
                        </button>
                      </td>
                      <td className="r num">{r.forecast_gco2_kwh}</td>
                      <td>{bandLabel(r.intensity_index)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </>
  )
}
