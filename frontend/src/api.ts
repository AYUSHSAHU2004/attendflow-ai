import type { components, paths } from './api.generated'
import { supervisorActor, workerActor } from './actors'

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

export async function startInvestigation(id: string, signal: AbortSignal) {
  const result = await request<InvestigationJob>(`${casePath(id)}/investigate`, supervisorActor.id, {
    method: 'POST', signal,
  })
  const path = result.response.headers.get('Location')
  if (!path?.startsWith(`${casePath(id)}/investigate/`)) {
    throw new Error('The API did not return a valid investigation polling URL.')
  }
  return path
}

export async function pollInvestigation(path: string, signal: AbortSignal) {
  return (await request<InvestigationJob>(path, supervisorActor.id, { signal })).body
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

export async function getCase(id: string, signal?: AbortSignal) {
  return (await request<SupervisorCase>(
    '/api/supervisor/cases/' + encodeURIComponent(id), supervisorActor.id, { signal },
  )).body
}

export async function approveCase(id: string, body: Schemas['ApproveIn']) {
  return (await request<ApproveResult>(`${casePath(id)}/approve`, supervisorActor.id, {
    method: 'POST', body: JSON.stringify(body),
  })).body
}

export async function editCase(id: string, body: Schemas['EditIn']) {
  return (await request<ApproveResult>(`${casePath(id)}/edit`, supervisorActor.id, {
    method: 'POST', body: JSON.stringify(body),
  })).body
}

export async function rejectCase(id: string, body: Schemas['RejectIn']) {
  return (await request<DecisionResult>(`${casePath(id)}/reject`, supervisorActor.id, {
    method: 'POST', body: JSON.stringify(body),
  })).body
}
