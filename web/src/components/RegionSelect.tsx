import type { Region } from '../lib/data'
import { setRegion, useRegion } from '../lib/region'

/** Dropdown of the 14 DNO regions plus the nations and GB. */
export default function RegionSelect({ regions }: { regions: Region[] }) {
  const selected = useRegion()
  const groups: [string, Region[]][] = [
    ['Regions', regions.filter((r) => r.region_type === 'dno')],
    ['Nations', regions.filter((r) => r.region_type !== 'dno')],
  ]
  return (
    <div>
      <label htmlFor="region">Your region</label>
      <select id="region" value={selected} onChange={(e) => setRegion(Number(e.target.value))}>
        {groups.map(([label, list]) => (
          <optgroup key={label} label={label}>
            {list.map((r) => (
              <option key={r.region_id} value={r.region_id}>{r.short_name}</option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  )
}
