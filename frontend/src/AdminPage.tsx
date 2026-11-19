import { useEffect, useRef, useState } from 'react'
import { adminActor } from './actors'
import {
  getAdminCase,
  getAdminOverview,
  pollInvestigation,
  startInvestigation,
  type AdminCase,
  type AdminCounters,
  type AdminFilters,
  type AdminOverview,
} from './api'
import { AutoFixPanel, AutoResolveMetricLine } from './AutoFix'
import { SchedulerPanel } from './SchedulerPanel'
import { CaseCard, noReplyBadge, plainError } from './SupervisorPage'
import { displayDate } from './WorkerInbox'

type Filters = Pick<AdminFilters, 'status' | 'policy_id' | 'team' | 'employee_id' | 'q' | 'no_reply'>

const NO_REPLY_LABELS: Record<string, string> = {
  any: 'Any step',
  reminded: 'Reminder sent',
  supervisor: 'With supervisor',
  payroll_admin: 'Sent to payroll',
}

const COUNTERS: { key: keyof AdminCounters; label: string; status?: AdminFilters['status'] }[] = [
  { key: 'total', label: 'All' },
  { key: 'open', label: 'Open', status: 'open' },
  { key: 'awaiting_worker', label: 'Waiting for worker', status: 'awaiting_worker' },
  { key: 'awaiting_supervisor', label: 'Waiting for supervisor', status: 'awaiting_supervisor' },
  { key: 'escalated', label: 'Escalated', status: 'escalated' },
  { key: 'resolved', label: 'Resolved', status: 'resolved' },
  { key: 'rejected', label: 'Rejected', status: 'rejected' },
  { key: 'auto_resolved', label: 'Auto-resolved' },
  { key: 'stuck', label: 'Stuck (no reply)' },
]

export function statusLabel(status: string) {
  return status.replace(/_/g, ' ')
}

function pause(signal: AbortSignal, ms = 750) {
  return new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => { clearTimeout(timer); resolve() }, { once: true })
  })
}

function adminError(error: unknown) {
  if (error && typeof error === 'object' && 'code' in error && error.code === 'admin_only') {
    return 'Only the payroll admin can open this page.'
  }
  return plainError(error)
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

// ---------------------------------------------------------------- detail panel

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title}>
      <h3>{title}</h3>
      {children}
    </section>
  )
}

export function AdminDetail({
  id,
  onChanged,
  onClose,
}: {
  id: string
  onChanged: () => void
  onClose: () => void
}) {
  const [data, setData] = useState<AdminCase | null>(null)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const [investigating, setInvestigating] = useState(false)
  const [notice, setNotice] = useState('')
  const [deciding, setDeciding] = useState(false)
  const running = useRef<AbortController | null>(null)
  useEffect(() => () => running.current?.abort(), [])

  useEffect(() => {
    const controller = new AbortController()
    getAdminCase(id, controller.signal)
      .then((body) => { if (!controller.signal.aborted) { setData(body); setError('') } })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(adminError(failure)) })
    return () => controller.abort()
  }, [id, reload])

  async function investigate() {
    const controller = new AbortController()
    running.current = controller
    setInvestigating(true)
    setNotice('')
    setError('')
    try {
      const location = await startInvestigation(id, controller.signal, adminActor.id)
      let job = await pollInvestigation(location, controller.signal, adminActor.id)
      while (job.status === 'running' && !controller.signal.aborted) {
        await pause(controller.signal)
        if (controller.signal.aborted) return
        job = await pollInvestigation(location, controller.signal, adminActor.id)
      }
      setNotice(job.status === 'failed'
        ? 'The investigation stopped; the engine template was stored instead.'
        : 'Investigation stored.')
      setReload((value) => value + 1)
      onChanged()
    } catch (failure) {
      if (!controller.signal.aborted) setError(adminError(failure))
    } finally {
      if (!controller.signal.aborted) setInvestigating(false)
    }
  }

  if (error && !data) {
    return <section className="panel case-card"><p role="alert" className="error">{error}</p></section>
  }
  if (!data) return <p role="status" className="panel">Loading the case…</p>

  const inv = data.investigation
  const recheck = data.recheck
  return (
    <article className="panel case-card admin-detail" aria-labelledby="admin-case-title">
      <div className="case-head">
        <div>
          <p className="eyebrow">{data.policy_id} · {data.severity} · {statusLabel(data.status)}</p>
          <h2 id="admin-case-title">{data.employee.name}, {displayDate(data.date)}</h2>
          <p className="hint">
            {data.employee.team} team · with {data.assigned_to_name ?? 'nobody'}
            {data.auto_resolved && ' · auto-resolved'}
          </p>
        </div>
        <button className="secondary small" onClick={onClose}>Close</button>
      </div>

      {data.auto_fix && (
        <AutoFixPanel
          info={data.auto_fix}
          exceptionId={data.exception_id}
          actor={adminActor.id}
          onUndone={(message) => {
            setNotice(message)
            setReload((value) => value + 1)
            onChanged()
          }}
        />
      )}

      {data.no_reply && (
        <section aria-label="No reply" className={data.no_reply.stage ? 'no-reply warn-box' : 'no-reply'}>
          <h3>{data.no_reply.label}</h3>
          <p>{data.no_reply.note}</p>
          <ul className="facts">
            {data.no_reply.wait_since && <li>Waiting since {data.no_reply.wait_since.slice(0, 16).replace('T', ' ')}</li>}
            {data.no_reply.reminded_at && <li>Reminder sent {data.no_reply.reminded_at.slice(0, 16).replace('T', ' ')}</li>}
            {data.no_reply.supervisor_at && <li>Supervisor brought in {data.no_reply.supervisor_at.slice(0, 16).replace('T', ' ')}</li>}
            {data.no_reply.admin_at && <li>Sent to payroll {data.no_reply.admin_at.slice(0, 16).replace('T', ' ')}</li>}
            {data.no_reply.late_reply_at && <li>Worker replied {data.no_reply.late_reply_at.slice(0, 16).replace('T', ' ')}</li>}
          </ul>
        </section>
      )}

      {data.needs_your_decision && (
        <div className="decision-callout" role="note">
          <strong>Needs your decision.</strong>{' '}
          {data.no_reply?.stage === 3
            ? 'The worker did not reply and the supervisor did not act in time.'
            : 'A supervisor sent it to you.'}
          {!deciding && (
            <button className="small" onClick={() => setDeciding(true)}>Open the decision card</button>
          )}
        </div>
      )}
      {deciding && (
        <CaseCard
          id={data.exception_id}
          actor={adminActor.id}
          onClose={() => setDeciding(false)}
          onChanged={(message, closeCard) => {
            if (message) setNotice(message)
            if (closeCard) setDeciding(false)
            setReload((value) => value + 1)
            onChanged()
          }}
        />
      )}

      {data.can_investigate && (
        <div className="actions">
          <button onClick={() => void investigate()} disabled={investigating}>
            {investigating ? 'Investigating…' : inv ? 'Investigate again' : 'Investigate'}
          </button>
        </div>
      )}
      {investigating && <p role="status" className="hint">The agent is reading the records. This takes a few seconds.</p>}
      {notice && <p role="status" className="notice">{notice}</p>}
      {error && <p role="alert" className="error">{error}</p>}

      <Section title="The issue">
        <p><strong>{data.title}</strong></p>
        <p>{data.summary}</p>
      </Section>

      <Section title={`Policy ${data.policy.policy_id}: ${data.policy.title}`}>
        <blockquote>{data.policy.cited_text}</blockquote>
      </Section>

      <Section title="Evidence">
        {data.evidence.length === 0 ? <p>No evidence rows.</p> : (
          <ul className="evidence-list">
            {data.evidence.map((row, index) => (
              <li key={index}>
                {Object.entries(row).map(([key, value]) => (
                  <span key={key}><span className="key">{key}</span> {cell(value)}</span>
                ))}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Investigation">
        {!inv ? <p>Not investigated yet.</p> : (
          <>
            <p>
              {inv.fallback
                ? <span className="badge warn">engine template</span>
                : <span className="badge ok">validated draft</span>}{' '}
              Confidence {inv.confidence}. Ask: <strong>{inv.who_to_ask}</strong>.
            </p>
            <p>{inv.what_happened}</p>
            <p className="hint">Next: {inv.next_action}</p>
            {inv.proposed_fix && <p className="hint">Proposed fix: {inv.proposed_fix.option_id}</p>}
            {inv.validation_result && (
              <p className="hint">
                Simulated: day {inv.validation_result.day_worked_hours ?? '–'} h, week{' '}
                {inv.validation_result.week_projected_hours} h,{' '}
                {inv.validation_result.new_violations.length} new violation(s).
              </p>
            )}
            {data.latest_job && <p className="hint">Last job: {data.latest_job.status} ({data.latest_job.reason ?? 'running'})</p>}
          </>
        )}
      </Section>

      <Section title="Worker message and reply">
        {data.worker_messages.length === 0 ? <p>The worker has not been asked.</p> : (
          data.worker_messages.map((m) => (
            <div key={m.id} className="message-block">
              <p className="hint">Sent ({m.source === 'llm' ? 'written by the LLM, validated' : 'template'})</p>
              <blockquote>{m.message}</blockquote>
              {m.reminded_at && <p className="hint">Reminder sent {m.reminded_at.slice(0, 16).replace('T', ' ')}: {m.reminder_text}</p>}
              {m.replied_at ? (
                <p>
                  Reply: <strong>{m.confirmed ? 'Yes' : 'No'}</strong>
                  {m.reply_text && <> — <q>{m.reply_text}</q></>}
                </p>
              ) : <p>No reply yet.</p>}
              {m.needs_actual_time && <p className="hint">Waiting for the worker to give the actual time.</p>}
            </div>
          ))
        )}
      </Section>

      {recheck && (
        <Section title="Re-check of the confirmed time">
          <p>
            Confirmed {recheck.timestamp.slice(11, 16)} ({recheck.source}
            {recheck.approximate ? ', approximate' : ''})
          </p>
          <p>{recheck.impact_note}</p>
        </Section>
      )}

      <Section title="Fix options">
        {data.options.length === 0 ? <p>No fix options.</p> : (
          <ul className="option-list">
            {data.options.map((option) => (
              <li key={option.option_id}>
                <strong>{option.label}</strong>
                <span>{option.description}</span>
                <span className={option.consequence.creates_violations ? 'consequence warn' : 'consequence'}>
                  {option.consequence.note}
                </span>
              </li>
            ))}
          </ul>
        )}
        {data.applied_fix && (
          <p className="notice">Applied: {cell(data.applied_fix.label ?? data.applied_fix.action)}</p>
        )}
      </Section>

      <Section title="Audit trail">
        <ol className="timeline">
          {data.audit_trail.map((entry) => (
            <li key={entry.id}>
              <span className="who">{entry.actor_name ?? entry.actor}</span>
              <span className="what">{entry.summary}</span>
              {entry.before_summary && entry.after_summary && entry.before_summary !== entry.after_summary && (
                <span className="hint">{entry.before_summary} → {entry.after_summary}</span>
              )}
              {entry.reason && <span className="hint">Reason: {entry.reason}</span>}
            </li>
          ))}
        </ol>
      </Section>

      {data.tool_calls.length > 0 && (
        <Section title="Tool calls">
          <ul className="tool-list">
            {data.tool_calls.map((call, index) => (
              <li key={index}>
                <code>{call.tool_name}</code> {call.ok ? 'ok' : `failed${call.error_code ? ` (${call.error_code})` : ''}`}
                {call.duration_ms !== null && call.duration_ms !== undefined && ` · ${Math.round(call.duration_ms)} ms`}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </article>
  )
}

// ---------------------------------------------------------------- page

export function AdminPage() {
  const [filters, setFilters] = useState<Filters>({})
  const [search, setSearch] = useState('')
  const [data, setData] = useState<AdminOverview | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)

  // The name search waits for a short pause in typing.
  useEffect(() => {
    const next = search.trim() || undefined
    const timer = setTimeout(() => setFilters((current) => (current.q === next ? current : { ...current, q: next })), 250)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    getAdminOverview(filters, controller.signal)
      .then((body) => { if (!controller.signal.aborted) { setData(body); setError('') } })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(adminError(failure)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [filters, refresh])

  function setFilter<K extends keyof Filters>(key: K, value: Filters[K] | '') {
    setFilters((current) => ({ ...current, [key]: value === '' ? undefined : value }))
  }

  const options = data?.filter_options
  const filtered = Boolean(filters.status || filters.policy_id || filters.team || filters.employee_id || filters.q || filters.no_reply)

  return (
    <main className="page wide admin" id="main">
      <h1>All exceptions</h1>
      <p className="lede">Signed in as {adminActor.name} ({adminActor.id})</p>

      <SchedulerPanel onChanged={() => setRefresh((value) => value + 1)} />

      <AutoResolveMetricLine refresh={refresh} />

      {data && (
        <section aria-label="Counters" className="counters">
          {COUNTERS.map((c) => (
            <button
              key={c.key}
              className={`counter ${(c.status && filters.status === c.status) || (c.key === 'stuck' && filters.no_reply) ? 'active' : ''}`}
              disabled={!c.status && c.key !== 'total' && c.key !== 'stuck'}
              onClick={() => (c.key === 'stuck'
                ? setFilters((current) => ({ ...current, status: undefined, no_reply: 'any' }))
                : setFilter('status', c.status ?? ''))}
              aria-label={`${c.label}: ${data.counters[c.key]}`}
            >
              <span className="count">{data.counters[c.key]}</span>
              <span className="label">{c.label}</span>
            </button>
          ))}
        </section>
      )}

      <form className="filters" aria-label="Filters" onSubmit={(event) => event.preventDefault()}>
        <label>
          Search
          <input
            type="search"
            placeholder="Name or ID"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <label>
          Status
          <select value={filters.status ?? ''} onChange={(event) => setFilter('status', event.target.value as Filters['status'])}>
            <option value="">Any</option>
            {(options?.statuses ?? []).map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
          </select>
        </label>
        <label>
          Policy
          <select value={filters.policy_id ?? ''} onChange={(event) => setFilter('policy_id', event.target.value)}>
            <option value="">Any</option>
            {(options?.policy_ids ?? []).map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label>
          Team
          <select value={filters.team ?? ''} onChange={(event) => setFilter('team', event.target.value)}>
            <option value="">Any</option>
            {(options?.teams ?? []).map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          Employee
          <select value={filters.employee_id ?? ''} onChange={(event) => setFilter('employee_id', event.target.value)}>
            <option value="">Anyone</option>
            {(options?.employees ?? []).map((e) => <option key={e.employee_id} value={e.employee_id}>{e.name}</option>)}
          </select>
        </label>
        <label>
          No reply
          <select value={filters.no_reply ?? ''} onChange={(event) => setFilter('no_reply', event.target.value as Filters['no_reply'])}>
            <option value="">Any case</option>
            {(options?.no_reply ?? []).map((value) => <option key={value} value={value}>{NO_REPLY_LABELS[value] ?? value}</option>)}
          </select>
        </label>
        <button
          type="button"
          className="secondary"
          disabled={!filtered}
          onClick={() => { setSearch(''); setFilters({}) }}
        >
          Clear filters
        </button>
      </form>

      <div className={selected ? 'admin-split with-detail' : 'admin-split'}>
        <section aria-label="Exceptions" className="admin-list">
          {error ? (
            <div className="panel">
              <p role="alert" className="error">{error}</p>
              <button onClick={() => setRefresh((value) => value + 1)}>Try again</button>
            </div>
          ) : !data ? (
            <p role="status" className="panel">Loading exceptions…</p>
          ) : data.items.length === 0 ? (
            <p className="panel">No exceptions match these filters.</p>
          ) : (
            <>
              <p className="hint" aria-live="polite">
                {loading ? 'Updating…' : `Showing ${data.items.length} of ${data.matched}`}
              </p>
              <table className="admin-table">
                <thead>
                  <tr>
                    <th scope="col">Employee</th>
                    <th scope="col">Date</th>
                    <th scope="col">Policy</th>
                    <th scope="col">Severity</th>
                    <th scope="col">Status</th>
                    <th scope="col">With</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr
                      key={item.exception_id}
                      className={item.exception_id === selected ? 'selected' : ''}
                      onClick={() => setSelected(item.exception_id)}
                    >
                      <td>
                        <button
                          className="link-button"
                          aria-label={`Open ${item.exception_id}`}
                          onClick={(event) => { event.stopPropagation(); setSelected(item.exception_id) }}
                        >
                          {item.employee_name}
                        </button>
                        <span className="hint block">{item.team}</span>
                      </td>
                      <td>{displayDate(item.date)}</td>
                      <td>
                        <strong>{item.policy_id}</strong> {item.kind === 'risk' && <span className="badge">risk</span>}
                        <span className="hint block">{item.title}</span>
                      </td>
                      <td><span className={`badge ${item.severity}`}>{item.severity}</span></td>
                      <td>
                        <span className={`status status-${item.status}`}>{statusLabel(item.status)}</span>
                        {item.auto_resolved && <span className="badge auto">auto</span>}
                        {item.auto_resolve_undone && <span className="badge warn">undone</span>}
                        {item.needs_your_decision && <span className="badge decide">Needs your decision</span>}
                        {item.no_reply && (
                          <span className={`badge ${item.no_reply.stage ? 'warn' : 'info'}`} title={item.no_reply.note}>
                            {item.no_reply.stage ? `${item.no_reply.label} · ${noReplyBadge(item.no_reply)}` : noReplyBadge(item.no_reply)}
                          </span>
                        )}
                      </td>
                      <td>
                        {item.assigned_to_name ?? '–'}
                        <span className="hint block">
                          {item.investigated ? `investigated → ${item.who_to_ask}` : 'not investigated'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
        {selected && (
          <AdminDetail
            key={selected}
            id={selected}
            onClose={() => setSelected(null)}
            onChanged={() => setRefresh((value) => value + 1)}
          />
        )}
      </div>
    </main>
  )
}
