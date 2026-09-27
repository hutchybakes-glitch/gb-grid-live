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

export interface AccuracyRow {
  grouping: 'overall' | 'month' | 'local_hour' | 'wind_regime'
  group_key: string
  n: number
  mae: number
  bias: number
  rmse: number
  mae_pct_of_mean: number
}

export interface BacktestRow {
  horizon: '1h_ahead' | '24h_ahead'
  fold: string
  train_rows: number | null
  n: number
  mae_official: number
  mae_model: number
  mae_recent_error: number
  bias_official: number
  bias_model: number
}

export interface Trust {
  accuracy: AccuracyRow[]
  snapshot_accuracy: { lead_bucket: string; min_lead_hours: number; n: number; snapshot_days: number; mae: number; bias: number }[]
  snapshot_days: { days: number; first: string | null; last: string | null }
  backtest: BacktestRow[]
  features: { horizon: string; feature: string; importance_share: number }[]
}

export interface InsightRow {
  card: 'cleanest_hour' | 'year_on_year' | 'region_gap'
  value_1: number
  value_2: number
  value_3: number | null
  value_4: number | null
  as_of_utc: string
}

export interface Explore {
  heatmap: { local_month: number; local_hour: number; avg_actual_gco2_kwh: number; n: number }[]
  league: { window_days: number; rank: number; region_id: number; short_name: string; n: number; avg_gco2_kwh: number; pct_low_or_very_low: number }[]
  solar: { season: 'summer' | 'winter'; slot: number; local_time: string; n: number; avg_solar_mw: number; avg_demand_mw: number | null; avg_actual_gco2_kwh: number }[]
  solar_peak: { at_utc: string; mw: number }
  insights: InsightRow[]
}

export interface SourceHealth {
  source: string
  raw_files: number
  bronze_rows: number
  silver_rows: number
  duplicates_removed: number
  areas: number
  first_period: string
  last_period: string
  missing_periods: number
  days_with_gaps: number
  completeness_pct: number
  snapshot_days: number
  built_at_utc: string
}

export interface PipelineHealth {
  sources: SourceHealth[]
  gap_days: { source: string; utc_date: string; missing_half_hours: number; areas: number }[]
  tests: { counts: Record<string, number>; tests: { name: string; status: string; failures: number | null }[] } | null
}
