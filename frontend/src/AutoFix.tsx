import { useEffect, useState } from 'react'
import { supervisorActor } from './actors'
import {
  ApiError,
  getAutoResolveMetric,
  getTeamAutoFixes,
  undoAutoResolve,
  type AutoFix,
  type AutoResolveMetric,
  type TeamAutoFix,
} from './api'
import { plainError } from './SupervisorPage'
import { displayDate } from './WorkerInbox'

const MIN_REASON = 10

function stamp(value: string | null | undefined) {
  return value ? value.slice(0, 16).replace('T', ' ') : ''
}

export function undoError(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'undo_conflict':
        return `Undo refused, nothing was changed: ${error.message}`
      case 'undo_unavailable':
        return 'This case was auto-resolved before undo existed, so there is nothing to restore. Run a demo reset.'
      case 'already_undone':
        return 'Someone already undid this case. It is with people now.'
      case 'not_auto_resolved':
        return 'This case was not auto-resolved, so there is nothing to undo.'
      case 'not_assigned':
        return 'This worker is not on your team, so you cannot undo their case.'
      default:
        break
    }
  }
  return plainError(error)
}

// ---------------------------------------------------------------- the headline metric

export function AutoResolveMetricLine({ refresh }: { refresh: number }) {
  const [metric, setMetric] = useState<AutoResolveMetric | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    getAutoResolveMetric(controller.signal)
      .then((body) => { if (!controller.signal.aborted) { setMetric(body); setError('') } })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(plainError(failure)) })
    return () => controller.abort()
  }, [refresh])

  if (error) return <p role="alert" className="error metric-line">{error}</p>
  if (!metric) return null
  const x = metric.resolved_without_human
  const y = metric.needed_handling
  return (
    <section aria-label="Resolved without a human" className="panel metric-panel">
      <p className="metric-headline">
        <strong>{x} of {y}</strong> exceptions resolved without a human
        <span className="metric-percent"> ({metric.percent}%)</span>
      </p>
      <p className="hint metric-detail">
        {metric.by_policy.filter((p) => p.auto_resolved || p.undone).map((p) => (
          `${p.policy_id}: ${p.auto_resolved} auto-resolved${p.undone ? `, ${p.undone} undone` : ''}`
        )).join(' · ') || 'Nothing auto-resolved yet.'}
        {!metric.auto_resolve_enabled && ' · Auto-resolve is switched off (AUTO_RESOLVE_ENABLED=false).'}
      </p>
      <p className="hint metric-footnote">
        Counted by code from the database. Undone cases count as human work.
        {metric.closed_by_data_change > 0 && (
          <> Not counted: {metric.closed_by_data_change} case{metric.closed_by_data_change === 1 ? '' : 's'} closed
          because the data changed (nobody had to act).</>
        )}
      </p>
    </section>
  )
}

// ---------------------------------------------------------------- one case

export function AutoFixPanel({
  info,
  exceptionId,
  actor,
  onUndone,
}: {
  info: AutoFix
  exceptionId: string
  actor: string
  onUndone: (message: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const short = reason.trim().length < MIN_REASON

  async function undo() {
    setBusy(true)
    setError('')
    try {
      const result = await undoAutoResolve(exceptionId, { reason: reason.trim() }, actor)
      const restored = result.restored.length
      setOpen(false)
      setReason('')
      onUndone(restored
        ? `Undone: ${restored} punch${restored === 1 ? '' : 'es'} restored. The case is open for a person.`
        : 'Undone. Nothing to restore; the case is open for a person.')
    } catch (failure) {
      setError(undoError(failure))
    } finally {
      setBusy(false)
    }
  }

  const title = info.state === 'auto_resolved'
    ? 'Auto-resolved by the system'
    : info.state === 'undone' ? 'Auto-resolve undone' : 'Not auto-resolved'
  return (
    <section aria-label="Auto-resolve" className={`auto-fix auto-fix-${info.state}`}>
      <p className="auto-fix-title">
        <span className={`badge ${info.state === 'auto_resolved' ? 'auto' : 'warn'}`}>
          {info.state === 'auto_resolved' ? 'auto-resolved' : info.state === 'undone' ? 'undone' : 'held'}
        </span>{' '}
        <strong>{title}</strong>
        {info.resolved_at && info.state === 'auto_resolved' && <span className="hint"> · {stamp(info.resolved_at)}</span>}
      </p>
      {info.basis && <p><span className="key">Why it was allowed:</span> {info.basis}.</p>}
      {info.held_because.length > 0 && info.state === 'held' && (
        <p><span className="key">Left for a person:</span> {info.held_because.join('; ')}.</p>
      )}
      {info.changes.length > 0 ? (
        <div>
          <span className="key">{info.state === 'undone' ? 'What it had changed:' : 'What it changed:'}</span>
          <ul className="evidence-list">{info.changes.map((line) => <li key={line}>{line}</li>)}</ul>
        </div>
      ) : info.state !== 'held' && <p><span className="key">What it changed:</span> no data (a decision only).</p>}
      {info.policy_quote && <blockquote>Policy: {info.policy_quote}</blockquote>}
      {info.state === 'undone' && (
        <p>
          Undone by <strong>{info.undone_by_name ?? info.undone_by}</strong>
          {info.undone_at && <> on {stamp(info.undone_at)}</>}
          {info.undo_reason && <>: <q>{info.undo_reason}</q></>}. A person decides it now.
        </p>
      )}
      {info.undo_unavailable_reason && <p className="hint">{info.undo_unavailable_reason}</p>}
      {info.last_refusal?.message && (
        <p className="hint">Last undo attempt was refused: {info.last_refusal.message}</p>
      )}
      {info.can_undo && !open && (
        <button className="secondary small" onClick={() => { setOpen(true); setError('') }}>Undo</button>
      )}
      {open && (
        <form className="reject-form" onSubmit={(event) => { event.preventDefault(); if (!short) void undo() }}>
          <label>
            Why undo it? (at least {MIN_REASON} characters, saved in the audit log)
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={2} />
          </label>
          <div className="actions">
            <button type="submit" className="danger" disabled={busy || short}>
              {busy ? 'Undoing…' : 'Confirm undo'}
            </button>
            <button type="button" className="secondary" disabled={busy} onClick={() => { setOpen(false); setError('') }}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="error">{error}</p>}
    </section>
  )
}

// ---------------------------------------------------------------- the supervisor's team

export function TeamAutoFixes({ refresh, onUndone }: { refresh: number; onUndone: (message: string) => void }) {
  const [items, setItems] = useState<TeamAutoFix[] | null>(null)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getTeamAutoFixes(controller.signal)
      .then((body) => { if (!controller.signal.aborted) { setItems(body); setError('') } })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(plainError(failure)) })
    return () => controller.abort()
  }, [refresh, reload])

  return (
    <section aria-label="Auto-resolved for my team" className="team-auto">
      <h2>Auto-resolved for my team</h2>
      {error ? <p role="alert" className="error">{error}</p>
        : items === null ? <p role="status" className="hint">Loading…</p>
          : items.length === 0 ? <p className="hint">Nothing was auto-resolved for your team.</p>
            : (
              <ul className="team-auto-list">
                {items.map((item) => (
                  <li key={item.exception_id}>
                    <strong>{item.employee_name}</strong>{' '}
                    <span className="hint">{item.policy_id} · {displayDate(item.date)}</span>
                    <p className="row-summary">{item.summary}</p>
                    {item.auto_fix && (
                      <AutoFixPanel
                        info={item.auto_fix}
                        exceptionId={item.exception_id}
                        actor={supervisorActor.id}
                        onUndone={(message) => { setReload((value) => value + 1); onUndone(message) }}
                      />
                    )}
                  </li>
                ))}
              </ul>
            )}
    </section>
  )
}
