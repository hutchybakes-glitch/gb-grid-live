// The plain-English summary sentence on the Now page.
import type { RegionNow } from './data'

const CLEAN = new Set(['wind', 'solar', 'nuclear', 'hydro', 'biomass'])

/** e.g. "North West England is cleaner than the GB average right now, mainly thanks to wind." */
export function nowSentence(r: RegionNow): string {
  const name = r.region_id === 18 ? 'Great Britain' : r.short_name
  if (r.region_id === 18) {
    return `Great Britain's grid is at ${r.forecast_gco2_kwh} gCO₂/kWh right now, with ${r.top_fuel} the largest source.`
  }
  const diff = r.diff_vs_gb
  // Within 5% of GB counts as "about the same" so small wobbles are not over-read.
  if (Math.abs(diff) <= Math.max(5, r.gb_forecast_gco2_kwh * 0.05)) {
    return `${name} is about the same as the GB average right now (${r.forecast_gco2_kwh} vs ${r.gb_forecast_gco2_kwh} gCO₂/kWh).`
  }
  const cleaner = diff < 0
  const fuelClause = cleaner
    ? CLEAN.has(r.top_fuel) ? `, mainly thanks to ${r.top_fuel}` : ''
    : CLEAN.has(r.top_fuel) ? '' : `, mainly because of ${r.top_fuel}`
  return `${name} is ${cleaner ? 'cleaner' : 'dirtier'} than the GB average right now (${r.forecast_gco2_kwh} vs ${r.gb_forecast_gco2_kwh} gCO₂/kWh)${fuelClause}.`
}
