// Page registry: one place for route ids, nav labels and titles.
export const PAGES = [
  { id: 'now', label: 'Now', title: 'Now' },
  { id: 'plan', label: 'Plan', title: 'Plan' },
  { id: 'trust', label: 'Trust', title: 'Trust the forecast?' },
  { id: 'explore', label: 'Explore', title: 'Explore' },
  { id: 'how', label: 'How it works', title: 'How it works' },
] as const

export type PageId = (typeof PAGES)[number]['id']

export function pageFromHash(hash: string): PageId {
  const id = hash.replace(/^#\/?/, '').split(/[/?]/)[0]
  return (PAGES.find((p) => p.id === id)?.id ?? 'now') as PageId
}
