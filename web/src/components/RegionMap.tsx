// A tile map of the 14 GB regions: each region is one square, placed roughly
// where it sits geographically. Every tile is a button, so the map works by
// keyboard and screen reader, and each shows its value as text, not only colour.
import type { RegionNow } from '../lib/data'
import { bandColour, bandLabel } from '../lib/palette'

/** Grid position (column, row) for each DNO region id. */
const TILES: Record<number, [number, number, string]> = {
  1: [1, 0, 'N Scot'],
  2: [1, 1, 'S Scot'],
  3: [1, 2, 'NW Eng'],
  4: [2, 2, 'NE Eng'],
  6: [0, 3, 'N Wales'],
  5: [2, 3, 'Yorks'],
  7: [0, 4, 'S Wales'],
  8: [1, 4, 'W Mids'],
  9: [2, 4, 'E Mids'],
  10: [3, 4, 'East'],
  11: [0, 5, 'SW Eng'],
  12: [1, 5, 'South'],
  13: [2, 5, 'London'],
  14: [3, 5, 'SE Eng'],
}

const SIZE = 64
const GAP = 6

interface Props {
  regions: RegionNow[]
  selected: number
  onSelect: (id: number) => void
}

export default function RegionMap({ regions, selected, onSelect }: Props) {
  const byId = new Map(regions.map((r) => [r.region_id, r]))
  const width = 4 * (SIZE + GAP)
  const height = 6 * (SIZE + GAP)
  return (
    <svg className="map" viewBox={`0 0 ${width} ${height}`} role="group" aria-label="Map of GB regions coloured by current carbon intensity. Select a region.">
      {Object.entries(TILES).map(([id, [col, row, abbr]]) => {
        const r = byId.get(Number(id))
        if (!r) return null
        const x = col * (SIZE + GAP)
        const y = row * (SIZE + GAP)
        const isSel = r.region_id === selected
        return (
          <g
            key={id}
            className="map-tile"
            role="button"
            tabIndex={0}
            aria-pressed={isSel}
            aria-label={`${r.short_name}: ${r.forecast_gco2_kwh} grams per kilowatt-hour, ${r.intensity_index}`}
            onClick={() => onSelect(r.region_id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSelect(r.region_id)
              }
            }}
            style={{ cursor: 'pointer' }}
          >
            <title>{`${r.short_name}: ${r.forecast_gco2_kwh} gCO₂/kWh (${bandLabel(r.intensity_index)})`}</title>
            <rect x={x} y={y} width={SIZE} height={SIZE} rx={8} fill={bandColour(r.intensity_index)} />
            <text x={x + SIZE / 2} y={y + 26} textAnchor="middle">{abbr}</text>
            <text x={x + SIZE / 2} y={y + 44} textAnchor="middle" className="num" style={{ fontSize: 14 }}>
              {r.forecast_gco2_kwh}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
