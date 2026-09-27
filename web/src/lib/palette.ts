// Fixed colours from DESIGN.md, shared by every chart and the map.

export type Band = 'very low' | 'low' | 'moderate' | 'high' | 'very high'

export const BANDS: Band[] = ['very low', 'low', 'moderate', 'high', 'very high']

export const BAND_COLOURS: Record<Band, string> = {
  'very low': '#1B9E77',
  low: '#66C2A5',
  moderate: '#F2C14E',
  high: '#F08A4B',
  'very high': '#D1495B',
}

export const FUEL_COLOURS: Record<string, string> = {
  wind: '#4FB3D9',
  solar: '#F2C14E',
  nuclear: '#9B7FD1',
  gas: '#8C96A3',
  biomass: '#6FA36B',
  hydro: '#3A7CA5',
  imports: '#C9A27E',
  coal: '#4A4A4A',
  other: '#B0B0B0',
}

/** Colour for a band name, tolerating unexpected values from the API. */
export function bandColour(band: string | null | undefined): string {
  return BAND_COLOURS[(band ?? '') as Band] ?? '#B0B0B0'
}

/** "very low" -> "Very low". */
export function bandLabel(band: string | null | undefined): string {
  if (!band) return 'Unknown'
  return band.charAt(0).toUpperCase() + band.slice(1)
}

/** Read a CSS custom property so charts follow the light/dark theme. */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
