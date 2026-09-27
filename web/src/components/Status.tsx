import type { Loadable } from '../lib/data'

/** Loading / error placeholder shared by every page. */
export default function Status({ states }: { states: Loadable<unknown>[] }) {
  const err = states.find((s) => s.status === 'error')
  if (err && err.status === 'error') {
    return <p role="alert">Sorry, the data could not be loaded: {err.error}</p>
  }
  return <p className="muted" aria-live="polite">Loading data…</p>
}

export function allReady(states: Loadable<unknown>[]): boolean {
  return states.every((s) => s.status === 'ready')
}
