// Loads the static JSON files written by pipeline/export.py.
import { useEffect, useState } from 'react'

export interface Region {
  region_id: number
  short_name: string
  dno_region: string
  region_type: 'dno' | 'nation' | 'gb'
}

export interface MixItem { fuel: string; perc: number }

export interface RegionNow {
  region_id: number
  short_name: string
  period_start_utc: string
  forecast_gco2_kwh: number
  intensity_index: string
  gb_forecast_gco2_kwh: number
  diff_vs_gb: number
  top_fuel: string
  generation_mix: MixItem[]
  captured_at: string
}

export interface Region48h {
  captured_at: string
  /** region id -> [period start ISO, gCO2/kWh, band] */
  regions: Record<string, [string, number, string][]>
}

export interface Meta { exported_at: string; data_last_updated: string }

const cache = new Map<string, Promise<unknown>>()

/** Fetch a data file once per page load. */
export function loadJson<T>(name: string): Promise<T> {
  if (!cache.has(name)) {
    const url = `${import.meta.env.BASE_URL}data/${name}`
    cache.set(
      name,
      fetch(url).then((r) => {
        if (!r.ok) throw new Error(`Could not load ${name} (HTTP ${r.status})`)
        return r.json()
      }),
    )
  }
  return cache.get(name) as Promise<T>
}

export type Loadable<T> = { status: 'loading' } | { status: 'error'; error: string } | { status: 'ready'; data: T }

/** React hook wrapper around loadJson. */
export function useData<T>(name: string): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ status: 'loading' })
  useEffect(() => {
    let live = true
    loadJson<T>(name)
      .then((data) => live && setState({ status: 'ready', data }))
      .catch((e: Error) => live && setState({ status: 'error', error: e.message }))
    return () => {
      live = false
    }
  }, [name])
  return state
}
