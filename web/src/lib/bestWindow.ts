// Best-window finder: the start time with the lowest average intensity.

export interface Point {
  /** Period start, milliseconds since epoch (UTC). */
  t: number
  /** Forecast intensity, gCO2/kWh. */
  v: number
}

export interface WindowResult {
  startIndex: number
  start: number
  /** End of the last half-hour in the window. */
  end: number
  avg: number
  /** Average if the task started at the first available slot instead. */
  nowAvg: number
}

const HALF_HOUR = 30 * 60 * 1000

/** Mean of v over points[i .. i+n-1], or null if those points are not consecutive half-hours. */
export function windowAverage(points: Point[], i: number, n: number): number | null {
  if (i < 0 || i + n > points.length || n < 1) return null
  let sum = 0
  for (let k = i; k < i + n; k++) {
    // A missing half-hour inside the window would make the average misleading.
    if (k > i && points[k].t - points[k - 1].t !== HALF_HOUR) return null
    sum += points[k].v
  }
  return sum / n
}

/**
 * Find the window of `slots` consecutive half-hours, starting at or after
 * `fromT`, with the lowest average intensity. Ties go to the earliest start,
 * because sooner is more useful and the forecast is more reliable.
 */
export function bestWindow(points: Point[], slots: number, fromT: number): WindowResult | null {
  const first = points.findIndex((p) => p.t + HALF_HOUR > fromT)
  if (first < 0) return null
  const nowAvg = windowAverage(points, first, slots)
  if (nowAvg === null) return null
  let best: WindowResult | null = null
  for (let i = first; i + slots <= points.length; i++) {
    const avg = windowAverage(points, i, slots)
    if (avg === null) continue
    if (best === null || avg < best.avg - 1e-9) {
      best = { startIndex: i, start: points[i].t, end: points[i + slots - 1].t + HALF_HOUR, avg, nowAvg }
    }
  }
  return best
}

/** Grams of CO2 saved by running at the best window rather than now. */
export function co2SavedGrams(result: WindowResult, kwh: number): number {
  return (result.nowAvg - result.avg) * kwh
}
