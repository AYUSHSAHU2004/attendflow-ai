import { type FormEvent, useEffect, useState } from 'react'
import { AdminDetail } from './AdminPage'
import { activityActor } from './actors'
import {
  getActivity,
  getActivitySummary,
  getAutonomy,
  type ActivityFilters,
  type ActivityItem,
  type ActivitySummary,
  type AutonomyRow,
} from './api'
import { CaseCard, plainError } from './SupervisorPage'

// Phase 14: the Activity Center. Every line comes from the audit log through the API, as a
// fixed-template sentence (no LLM). The API decides what this viewer may see.

type Filters = Pick<ActivityFilters, 'actor_type' | 'mode' | 'policy_id' | 'date_from' | 'date_to'> & {
  subject?: string
}
type Counts = ActivitySummary['counts']

const ACTOR_TYPES: { value: NonNullable<ActivityFilters['actor_type']>; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'agent', label: 'LLM agent' },
  { value: 'device', label: 'Device' },
  { value: 'worker', label: 'Worker' },
  { value: 'supervisor', label: 'Supervisor' },
  { value: 'admin', label: 'Payroll admin' },
]
const POLICIES = Array.from({ length: 17 }, (_, i) => `P${i + 1}`)
const SUMMARY: { key: keyof Counts; label: string }[] = [
  { key: 'investigated', label: 'Cases investigated by the agent' },
  { key: 'messages_sent', label: 'Messages sent' },
  { key: 'reminders_sent', label: 'Reminders' },
  { key: 'auto_resolved', label: 'Auto-resolved' },
  { key: 'escalated_by_silence', label: 'Escalated by silence' },
  { key: 'human_approvals', label: 'Human approvals' },
  { key: 'human_rejections', label: 'Human rejections' },
]
const ACTOR_CLASS: Record<string, string> = {
  system: 'actor-system', agent: 'actor-agent', device: 'actor-device',
  worker: 'actor-human', supervisor: 'actor-human', admin: 'actor-human',
}

export function whenText(stamp: string): string {
  const date = new Date(stamp.slice(0, 10) + 'T00:00:00Z')
  const day = new Intl.DateTimeFormat('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC',
  }).format(date)
  return `${day}, ${stamp.slice(11, 16)}`
}

// A case or employee ID typed in one box: E004 is an employee, anything else a case.
function subjectQuery(subject: string | undefined): Partial<ActivityFilters> {
  const value = subject?.trim()
  if (!value) return {}
  return /^E\d{3}$/i.test(value) ? { employee_id: value.toUpperCase() } : { exception_id: value }
}

function apiFilters(filters: Filters): ActivityFilters {
  const { subject, ...rest } = filters
  return { ...rest, ...subjectQuery(subject) }
}

function SummaryStrip({ summary, admin }: { summary: ActivitySummary | null; admin: boolean }) {
  if (!summary) return <p className="hint" role="status">Counting…</p>
  const c = summary.counts
  return (
    <section aria-label="Summary" className="counters activity-summary">
      {SUMMARY.map((item) => (
        <div key={item.key} className="counter" aria-label={`${item.label}: ${c[item.key]}`}>
          <span className="count">{c[item.key]}</span>
          <span className="label">
            {item.label}
            {item.key === 'auto_resolved' && c.auto_resolves_undone > 0 && ` (${c.auto_resolves_undone} undone)`}
            {item.key === 'human_approvals' && c.decided_without_worker > 0 && ` (${c.decided_without_worker} without the worker)`}
          </span>
        </div>
      ))}
      {admin && (
        <div className="counter" aria-label={`Device punches: ${c.device_punches}`}>
          <span className="count">{c.device_punches}</span>
          <span className="label">Device punches</span>
        </div>
      )}
    </section>
  )
}

function FeedRow({ item, onOpen }: { item: ActivityItem; onOpen: (id: string) => void }) {
  return (
    <li className={`feed-row ${ACTOR_CLASS[item.actor_type] ?? ''}`}>
      <time dateTime={item.at} className="feed-time">{whenText(item.at)}</time>
      <span className="feed-actor">
        <span className="badge actor-badge">{item.actor_label}</span>
        {item.actor_name !== item.actor_label && <span className="feed-name">{item.actor_name}</span>}
      </span>
      <span className="feed-sentence">
        {item.sentence}
        {item.reason && <span className="hint block">Reason: {item.reason}</span>}
      </span>
      <span className="feed-case">
        {item.case ? (
          <button
            className="link-button"
            aria-label={`Open case ${item.case.exception_id}`}
            onClick={() => onOpen(item.case!.exception_id)}
          >
            {item.employee?.name ?? item.case.exception_id} · {item.case.policy_id}
          </button>
        ) : item.employee ? (
          <span>{item.employee.name}</span>
        ) : null}
        {item.case && <span className="hint block">{item.case.title}</span>}
      </span>
    </li>
  )
}

function Feed({ admin }: { admin: boolean }) {
  const [filters, setFilters] = useState<Filters>({})
  const [subject, setSubject] = useState('')
  const [items, setItems] = useState<ActivityItem[] | null>(null)
  const [next, setNext] = useState<number | null>(null)
  const [summary, setSummary] = useState<ActivitySummary | null>(null)
  const [error, setError] = useState('')
  const [loadingMore, setLoadingMore] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const query = apiFilters(filters)
    setItems(null)
    Promise.all([
      getActivity(query, activityActor.id, controller.signal),
      getActivitySummary({
        policy_id: query.policy_id,
        employee_id: query.employee_id,
        exception_id: query.exception_id,
        date_from: query.date_from,
        date_to: query.date_to,
      }, activityActor.id, controller.signal),
    ])
      .then(([feed, counts]) => {
        if (controller.signal.aborted) return
        setItems(feed.items)
        setNext(feed.next_before_id)
        setSummary(counts)
        setError('')
      })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(activityError(failure)) })
    return () => controller.abort()
  }, [filters, refresh])

  async function loadOlder() {
    if (next === null) return
    setLoadingMore(true)
    try {
      const page = await getActivity({ ...apiFilters(filters), before_id: next })
      setItems((current) => [...(current ?? []), ...page.items])
      setNext(page.next_before_id)
    } catch (failure) {
      setError(activityError(failure))
    } finally {
      setLoadingMore(false)
    }
  }

  function setFilter<K extends keyof Filters>(key: K, value: Filters[K] | '') {
    setFilters((current) => ({ ...current, [key]: value === '' ? undefined : value }))
  }

  function applySubject(event: FormEvent) {
    event.preventDefault()
    setFilter('subject', subject.trim())
  }

  const filtered = Object.values(filters).some((value) => value !== undefined && value !== '')

  return (
    <>
      <SummaryStrip summary={summary} admin={admin} />

      <form className="filters" aria-label="Filters" onSubmit={applySubject}>
        <label>
          Who
          <select value={filters.actor_type ?? ''}
            onChange={(event) => setFilter('actor_type', event.target.value as Filters['actor_type'])}>
            <option value="">Anyone</option>
            {ACTOR_TYPES.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
          </select>
        </label>
        <label>
          Show
          <select value={filters.mode ?? 'all'}
            onChange={(event) => setFilter('mode', event.target.value === 'all' ? '' : event.target.value as Filters['mode'])}>
            <option value="all">Everything</option>
            <option value="autonomous">Autonomous only</option>
            <option value="human">Human decisions only</option>
          </select>
        </label>
        <label>
          Policy
          <select value={filters.policy_id ?? ''} onChange={(event) => setFilter('policy_id', event.target.value)}>
            <option value="">Any</option>
            {POLICIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label>
          Case or employee
          <input type="search" placeholder="E004 or P1-E004-…" value={subject}
            onChange={(event) => setSubject(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') { event.preventDefault(); setFilter('subject', subject.trim()) }
            }}
            onBlur={() => setFilter('subject', subject.trim())} />
        </label>
        <label>
          From
          <input type="date" value={filters.date_from ?? ''} onChange={(event) => setFilter('date_from', event.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={filters.date_to ?? ''} onChange={(event) => setFilter('date_to', event.target.value)} />
        </label>
        <button type="button" className="secondary" disabled={!filtered}
          onClick={() => { setSubject(''); setFilters({}) }}>
          Clear filters
        </button>
      </form>

      <div className={selected ? 'admin-split with-detail' : 'admin-split'}>
        <section aria-label="Activity feed" className="admin-list">
          {error ? (
            <div className="panel">
              <p role="alert" className="error">{error}</p>
              <button onClick={() => setRefresh((value) => value + 1)}>Try again</button>
            </div>
          ) : items === null ? (
            <p role="status" className="panel">Loading activity…</p>
          ) : items.length === 0 ? (
            <p className="panel">{filtered ? 'Nothing matches these filters.' : 'Nothing has happened yet.'}</p>
          ) : (
            <>
              <ol className="feed" aria-label="Events, newest first">
                {items.map((item) => <FeedRow key={item.id} item={item} onOpen={setSelected} />)}
              </ol>
              {next !== null && (
                <button className="secondary" disabled={loadingMore} onClick={() => void loadOlder()}>
                  {loadingMore ? 'Loading…' : 'Load older'}
                </button>
              )}
            </>
          )}
        </section>
        {selected && (admin ? (
          <AdminDetail
            key={selected}
            id={selected}
            onClose={() => setSelected(null)}
            onChanged={() => setRefresh((value) => value + 1)}
          />
        ) : (
          <CaseCard
            key={selected}
            id={selected}
            actor={activityActor.id}
            onClose={() => setSelected(null)}
            onChanged={() => setRefresh((value) => value + 1)}
          />
        ))}
      </div>
    </>
  )
}

function AutonomyTable() {
  const [rows, setRows] = useState<AutonomyRow[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    getAutonomy(activityActor.id, controller.signal)
      .then((items) => { if (!controller.signal.aborted) setRows(items) })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(activityError(failure)) })
    return () => controller.abort()
  }, [])
  if (error) return <p role="alert" className="error">{error}</p>
  if (!rows) return <p role="status" className="panel">Loading the autonomy table…</p>
  const allowed = rows.filter((r) => r.kind === 'allowed')
  const never = rows.filter((r) => r.kind === 'never')
  return (
    <section aria-label="Autonomy table" className="autonomy">
      <p className="lede">
        Every action the system can take, who may take it, and what stops it. Generated from
        the code; tests fail if it drifts.
      </p>
      <div className="admin-list">
        <table className="admin-table autonomy-table">
          <thead>
            <tr>
              <th scope="col">Action</th>
              <th scope="col">Actor</th>
              <th scope="col">Approval needed</th>
              <th scope="col">Reversible</th>
              <th scope="col">Guardrail</th>
            </tr>
          </thead>
          <tbody>
            {allowed.map((row) => (
              <tr key={row.key}>
                <td><strong>{row.title}</strong></td>
                <td>
                  <span className={`badge ${row.autonomous ? 'auto' : 'ok'}`}>{row.actor_label}</span>
                  <span className="hint block">{row.performed_by}</span>
                </td>
                <td>{row.approval_label}</td>
                <td>{row.reversible_label}</td>
                <td>{row.guardrail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2 className="never-title">Never allowed</h2>
      <ul className="never-list">
        {never.map((row) => (
          <li key={row.key}>
            <strong>{row.performed_by === 'Anyone' ? 'Nobody may' : `${row.performed_by}: never`}</strong>{' '}
            {row.title.charAt(0).toLowerCase() + row.title.slice(1)}. <span className="hint">{row.guardrail}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function activityError(error: unknown): string {
  if (error && typeof error === 'object' && 'code' in error && error.code === 'supervisor_only') {
    return 'Only supervisors and the payroll admin can see the activity.'
  }
  return plainError(error)
}

export function ActivityPage() {
  const [tab, setTab] = useState<'feed' | 'autonomy'>('feed')
  const admin = activityActor.role ? activityActor.role === 'payroll_admin' : activityActor.id === 'E201'
  return (
    <main className="page wide activity" id="main">
      <h1>Activity</h1>
      <p className="lede">
        Signed in as {activityActor.name} ({activityActor.id}).{' '}
        {admin ? 'You see everything.' : 'You see your team’s cases only.'}
      </p>
      <div role="tablist" aria-label="Activity views" className="tabs">
        <button role="tab" aria-selected={tab === 'feed'} className={tab === 'feed' ? 'tab active' : 'tab'}
          onClick={() => setTab('feed')}>What happened</button>
        <button role="tab" aria-selected={tab === 'autonomy'} className={tab === 'autonomy' ? 'tab active' : 'tab'}
          onClick={() => setTab('autonomy')}>Autonomy</button>
      </div>
      {tab === 'feed' ? <Feed admin={admin} /> : <AutonomyTable />}
    </main>
  )
}
