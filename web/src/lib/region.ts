// The selected region, shared across pages and remembered for the session.
import { useSyncExternalStore } from 'react'

export const DEFAULT_REGION = 3 // North West England (SPEC.md)
const KEY = 'gbgl-region'
const listeners = new Set<() => void>()

function read(): number {
  try {
    const v = Number(sessionStorage.getItem(KEY))
    return Number.isInteger(v) && v >= 1 && v <= 18 ? v : DEFAULT_REGION
  } catch {
    return DEFAULT_REGION
  }
}

let selected = read()

export function setRegion(id: number): void {
  selected = id
  try {
    sessionStorage.setItem(KEY, String(id))
  } catch {
    // Storage blocked: the choice still holds until the page is reloaded.
  }
  listeners.forEach((l) => l())
}

export function useRegion(): number {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => selected,
  )
}
