import type { components, paths } from './api.generated'
import { supervisorActor, workerActor } from './actors'

type Schemas = components['schemas']
type ReplyInput = paths['/api/exceptions/{exception_id}/worker-reply']['post']['requestBody']['content']['application/json']
export type WorkerMessage = Schemas['WorkerMessageOut']
export type InvestigationJob = Schemas['InvestigationJobOut']
export type InvestigationCase = Schemas['InvestigationCase']

const base = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

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
    throw new Error(problem?.error?.message ?? `Request failed (${response.status}).`)
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
