import { describe, expect, it } from 'vitest'
import { bestWindow, co2SavedGrams, windowAverage, type Point } from './bestWindow'

const HH = 30 * 60 * 1000
const T0 = Date.UTC(2026, 8, 27, 12, 0)
const series = (values: number[], start = T0): Point[] => values.map((v, i) => ({ t: start + i * HH, v }))

describe('bestWindow', () => {
  // Known series: the cleanest 2-slot window is at index 4-5 (avg 15).
  const pts = series([100, 90, 80, 50, 10, 20, 60, 70])

  it('finds the lowest-average window of the requested length', () => {
    const r = bestWindow(pts, 2, T0)!
    expect(r.startIndex).toBe(4)
    expect(r.avg).toBe(15)
    expect(r.nowAvg).toBe(95)
    expect(r.start).toBe(T0 + 4 * HH)
    expect(r.end).toBe(T0 + 6 * HH)
  })

  it('handles a 4-slot window (2 hours)', () => {
    const r = bestWindow(pts, 4, T0)!
    expect(r.startIndex).toBe(3) // 50,10,20,60 = 35 beats 80,50,10,20 = 40
    expect(r.avg).toBe(35)
  })

  it('never starts before the current half-hour', () => {
    const r = bestWindow(series([10, 10, 90, 90, 50, 50]), 2, T0 + 2 * HH + 5 * 60 * 1000)!
    expect(r.startIndex).toBe(4)
    expect(r.nowAvg).toBe(90)
  })

  it('breaks ties by choosing the earliest start', () => {
    expect(bestWindow(series([30, 30, 30, 30]), 2, T0)!.startIndex).toBe(0)
  })

  it('skips windows that span a missing half-hour', () => {
    const gappy: Point[] = [...series([100, 5]), ...series([5, 100, 100], T0 + 3 * HH)]
    // slots 1 and 2 are both 5 but not consecutive (gap at T0+2HH).
    const r = bestWindow(gappy, 2, T0)!
    expect(r.avg).not.toBe(5)
    expect(windowAverage(gappy, 1, 2)).toBeNull()
  })

  it('returns null when the task is longer than the forecast', () => {
    expect(bestWindow(pts, 9, T0)).toBeNull()
  })

  it('computes CO2 saved from the kWh assumption', () => {
    const r = bestWindow(pts, 2, T0)!
    expect(co2SavedGrams(r, 28)).toBe((95 - 15) * 28)
  })
})
