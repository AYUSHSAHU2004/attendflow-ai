// Local demo identity: the one place that says who is acting. The Phase 15 role switcher
// replaces this module.
export type Actor = { id: string; name: string }

export const workerActor: Actor = { id: 'E001', name: 'Amit Verma' }

export const reviewers: Record<string, Actor> = {
  E101: { id: 'E101', name: 'Ravi Kumar' },
  E102: { id: 'E102', name: 'Sunita Rao' },
  E201: { id: 'E201', name: 'Priya Sharma' },
}

const defaultReviewer = reviewers.E101

// Dev builds only: `?as=E102` (or E201) acts as another reviewer for demos and the live
// check. Production builds ignore it: import.meta.env.DEV is the constant false there, so
// Vite drops the branch and the lookup from the bundle. Review again in Phase 22.
export function reviewerFor(search: string, dev: boolean): Actor {
  if (!dev) return defaultReviewer
  const wanted = new URLSearchParams(search).get('as')?.toUpperCase() ?? ''
  return reviewers[wanted] ?? defaultReviewer
}

export const supervisorActor: Actor = import.meta.env.DEV
  ? reviewerFor(typeof window === 'undefined' ? '' : window.location.search, true)
  : defaultReviewer
