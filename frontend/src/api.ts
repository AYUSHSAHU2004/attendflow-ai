import type { components, paths } from './api.generated'
import { adminActor, supervisorActor, workerActor } from './actors'

type Schemas = components['schemas']
type ReplyInput = paths['/api/exceptions/{exception_id}/worker-reply']['post']['requestBody']['content']['application/json']
export type WorkerMessage = Schemas['WorkerMessageOut']
export type WorkerReceipt = Schemas['WorkerReplyOut']
export type InvestigationJob = Schemas['InvestigationJobOut']
export type InvestigationCase = Schemas['InvestigationCase']

export type QueueItem = Schemas['SupervisorQueueItemOut']
export type SupervisorCase = Schemas['SupervisorCaseOut']
export type CaseOption = Schemas['CardOptionOut']
export type ApproveResult = Schemas['ApproveOut']
export type DecisionResult = Schemas['ExceptionDetailOut']

export type AdminOverview = Schemas['AdminOverviewOut']
export type AdminItem = Schemas['AdminListItemOut']
export type AdminCase = Schemas['AdminCaseOut']
export type AdminCounters = Schemas['AdminCountersOut']
export type AdminFilters = NonNullable<paths['/api/admin/exceptions']['get']['parameters']['query']>

const base = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

// Keeps the shared error shape ({error: {code, message, details}}) so pages can explain it.
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

async function request<T>(
  path: string,
  actor: string,
  options: RequestInit = {},
): Promise<{ body: T; response: Response }> {
  const headers = new Headers(options.headers)
  headers.set('X-Actor-Id', actor)
  if (options.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(base + path, { ...options, headers })
  if (!response.ok) {
    const problem = await response.json().catch(() => null) as Schemas['ErrorResponse'] | null
    throw new ApiError(
      response.status,
      problem?.error?.code ?? 'http_error',
      problem?.error?.message ?? `Request failed (${response.status}).`,
      problem?.error?.details ?? null,
    )
  }
  return { body: await response.json() as T, response }
}

function casePath(id: string): string {
  return '/api/exceptions/' + encodeURIComponent(id)
}

export async function getWorkerMessages(signal?: AbortSignal) {
  return (await request<Schemas['WorkerInboxOut']>(
    '/api/worker/messages', workerActor.id, { signal },
  )).body.items
}

export async function sendReply(id: string, reply: ReplyInput) {
  return (await request<Schemas['WorkerReplyOut']>(`${casePath(id)}/worker-reply`, workerActor.id, {
    method: 'POST',
    body: JSON.stringify(reply),
  })).body
}

export async function confirmWorkerTime(id: string) {
  return (await request<WorkerReceipt>(`${casePath(id)}/worker-confirm-time`, workerActor.id, {
    method: 'POST',
  })).body
}

export async function submitManualTime(id: string, body: Schemas['WorkerTimeIn']) {
  return (await request<WorkerReceipt>(`${casePath(id)}/worker-manual-time`, workerActor.id, {
    method: 'POST', body: JSON.stringify(body),
  })).body
}

export async function startInvestigation(id: string, signal: AbortSignal, actor = supervisorActor.id) {
  const result = await request<InvestigationJob>(`${casePath(id)}/investigate`, actor, {
    method: 'POST', signal,
  })
  const path = result.response.headers.get('Location')
  if (!path?.startsWith(`${casePath(id)}/investigate/`)) {
    throw new Error('The API did not return a valid investigation polling URL.')
  }
  return path
}

export async function pollInvestigation(path: string, signal: AbortSignal, actor = supervisorActor.id) {
  return (await request<InvestigationJob>(path, actor, { signal })).body
}

export async function getInvestigation(id: string, signal: AbortSignal) {
  return (await request<Schemas['ExceptionDetailOut']>(
    casePath(id), supervisorActor.id, { signal },
  )).body.investigation_case ?? null
}

export async function askWorker(id: string, signal: AbortSignal) {
  const body: Schemas['AskWorkerIn'] = {}
  await request<Schemas['ExceptionDetailOut']>(`${casePath(id)}/ask-worker`, supervisorActor.id, {
    method: 'POST', body: JSON.stringify(body), signal,
  })
}

// ---------------------------------------------------------------- supervisor

export async function getQueue(signal?: AbortSignal) {
  return (await request<Schemas['SupervisorQueueOut']>(
    '/api/supervisor/queue', supervisorActor.id, { signal },
  )).body.items
}

export async function getCase(id: string, signal?: AbortSignal, actor = supervisorActor.id) {
  return (await request<SupervisorCase>(
    '/api/supervisor/cases/' + encodeURIComponent(id), actor, { signal },
  )).body
}

export async function approveCase(id: string, body: Schemas['ApproveIn'], actor = supervisorActor.id) {
  return (await request<ApproveResult>(`${casePath(id)}/approve`, actor, {
    method: 'POST', body: JSON.stringify(body),
  })).body
}

export async function editCase(id: string, body: Schemas['EditIn'], actor = supervisorActor.id) {
  return (await request<ApproveResult>(`${casePath(id)}/edit`, actor, {
    method: 'POST', body: JSON.stringify(body),
  })).body
}

export async function rejectCase(id: string, body: Schemas['RejectIn'], actor = supervisorActor.id) {
  return (await request<DecisionResult>(`${casePath(id)}/reject`, actor, {
    method: 'POST', body: JSON.stringify(body),
  })).body
}

// ---------------------------------------------------------------- payroll admin

export async function getAdminOverview(filters: AdminFilters, signal?: AbortSignal) {
  // Built by hand: the Phase 22 check greps the bundle for URLSearchParams (dev-only ?as=).
  const query = Object.entries(filters)
    .filter(([, value]) => value !== undefined && value !== null && String(value) !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
  const suffix = query.length ? `?${query.join('&')}` : ''
  return (await request<AdminOverview>('/api/admin/exceptions' + suffix, adminActor.id, { signal })).body
}

export async function getAdminCase(id: string, signal?: AbortSignal) {
  return (await request<AdminCase>(
    '/api/admin/exceptions/' + encodeURIComponent(id), adminActor.id, { signal },
  )).body
}

// ---------------------------------------------------------------- scheduler and demo (Phase 11)

export type SchedulerStatus = Schemas['SchedulerStatusOut']
export type SchedulerCycle = Schemas['SchedulerCycleOut']
export type PunchInput = Schemas['DemoPunchIn']
export type PunchAccepted = Schemas['PunchAcceptedOut']

export async function getSchedulerStatus(signal?: AbortSignal) {
  return (await request<SchedulerStatus>('/api/admin/scheduler', adminActor.id, { signal })).body
}

export async function runSchedulerNow() {
  return (await request<SchedulerCycle>('/api/admin/scheduler/run-now', adminActor.id, {
    method: 'POST',
  })).body
}

// DEMO_MODE only: the server has no such route otherwise (404).
export async function sendDemoPunch(body: PunchInput) {
  return (await request<PunchAccepted>('/api/admin/demo/punch', adminActor.id, {
    method: 'POST', body: JSON.stringify(body),
  })).body
}

// ---------------------------------------------------------------- auto-resolve (Phase 12)

export type AutoResolveMetric = Schemas['AutoResolveMetricOut']
export type AutoFix = Schemas['AutoFixOut']
export type TeamAutoFix = Schemas['TeamAutoFixItemOut']
export type UndoResult = Schemas['UndoOut']

export async function getAutoResolveMetric(signal?: AbortSignal) {
  return (await request<AutoResolveMetric>(
    '/api/admin/metrics/auto-resolve', adminActor.id, { signal },
  )).body
}

export async function undoAutoResolve(id: string, body: Schemas['UndoIn'], actor: string) {
  return (await request<UndoResult>(`${casePath(id)}/undo`, actor, {
    method: 'POST', body: JSON.stringify(body),
  })).body
}

export async function getTeamAutoFixes(signal?: AbortSignal, actor = supervisorActor.id) {
  return (await request<Schemas['TeamAutoFixesOut']>(
    '/api/supervisor/auto-resolved', actor, { signal },
  )).body.items
}
