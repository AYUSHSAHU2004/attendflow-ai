// Local demo identity: the one place that says who is acting.
export type Actor = { id: string; name: string }

const defaultWorker: Actor = { id: 'E001', name: 'Amit Verma' }

// Workers a dev build can act as with `?as=` on the inbox (Phase 11 demo: Neha gets the
// message the scheduler sends after a simulated punch). Phase 22 checklist.
export const workers: Record<string, Actor> = {
  E001: defaultWorker,
  E004: { id: 'E004', name: 'Neha Gupta' },
}

export const reviewers: Record<string, Actor> = {
  E101: { id: 'E101', name: 'Ravi Kumar' },
  E102: { id: 'E102', name: 'Sunita Rao' },
  E201: { id: 'E201', name: 'Priya Sharma' },
}

const defaultReviewer = reviewers.E101

// Dev builds only: `?as=E102` (or E201) acts as another reviewer for demos and the live
// check. Production builds ignore it: import.meta.env.DEV is the constant false there, so
// Vite drops the branch and the lookup from the bundle. Review again in Phase 22.
export function reviewerFor(search: string, dev: boolean, fallback: Actor = defaultReviewer): Actor {
  if (!dev) return fallback
  const wanted = new URLSearchParams(search).get('as')?.toUpperCase() ?? ''
  return reviewers[wanted] ?? fallback
}

const search = typeof window === 'undefined' ? '' : window.location.search

export const supervisorActor: Actor = import.meta.env.DEV
  ? reviewerFor(search, true)
  : defaultReviewer

// The payroll admin page (/admin) acts as Priya. In dev builds `?as=E101` shows how the
// page refuses anyone else (the API answers 403 admin_only).
const defaultAdmin = reviewers.E201

export const adminActor: Actor = import.meta.env.DEV
  ? reviewerFor(search, true, defaultAdmin)
  : defaultAdmin

// The worker inbox (/) acts as Amit. Dev builds only: `?as=E004` acts as Neha. Production
// builds drop the branch (import.meta.env.DEV is the constant false), like the reviewer one.
export function workerFor(search: string, dev: boolean): Actor {
  if (!dev) return defaultWorker
  const wanted = new URLSearchParams(search).get('as')?.toUpperCase() ?? ''
  return workers[wanted] ?? defaultWorker
}

export const workerActor: Actor = import.meta.env.DEV ? workerFor(search, true) : defaultWorker

// The Activity Center (/activity, Phase 14) acts as Priya, who sees everything. Dev builds
// only: `?as=E101` (or E102) shows a supervisor's team-only view. The API enforces the scope.
export const activityActor: Actor = adminActor

export const supervisorDashboardPath = '/supervisor/dashboard'
export const dashboardActor: Actor =
  typeof window !== 'undefined' && window.location.pathname === supervisorDashboardPath
    ? supervisorActor
    : adminActor

export const teamDashboardHref = import.meta.env.DEV
  ? `${supervisorDashboardPath}?as=${supervisorActor.id}`
  : supervisorDashboardPath
