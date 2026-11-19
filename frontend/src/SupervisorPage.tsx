import { type FormEvent, useEffect, useState } from 'react'
import { supervisorActor } from './actors'
import {
  ApiError,
  approveCase,
  editCase,
  escalateCase,
  getCase,
  getQueue,
  rejectCase,
  type ApproveResult,
  type CaseOption,
  type NoReply,
  type QueueItem,
  type SupervisorCase,
} from './api'
import { displayDate } from './WorkerInbox'
import { TeamAutoFixes } from './AutoFix'

const TIME_ACTIONS = new Set(['set_clock_out', 'set_clock_in', 'correct_clock_out'])
const MIN_REJECT = 10
const MIN_EDIT_REASON = 3
const MIN_WITHOUT_REASON = 10
const MIN_ESCALATE = 10

type Mode = 'idle' | 'confirm' | 'edit' | 'reject' | 'escalate'
type Finding = SupervisorCase['options'][number]['consequence']['new_violations'][number]

function firstName(name: string) {
  return name.split(' ')[0] || name
}

function hhmm(stamp: string | null | undefined) {
  return stamp ? stamp.slice(11, 16) : ''
}

function stampText(stamp: string) {
  return `${hhmm(stamp)} on ${displayDate(stamp.slice(0, 10))}`
}

function detailText(details: unknown) {
  if (!Array.isArray(details)) return ''
  return details
    .map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : ''))
    .filter(Boolean)
    .join('; ')
}

/** Every refusal in plain words. Codes come from the API's shared error shape. */
export function plainError(error: unknown, workerName = 'The worker', timeOption = false): string {
  if (!(error instanceof ApiError)) {
    if (error instanceof TypeError) return 'The server could not be reached. Check that the API is running.'
    return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
  }
  const who = firstName(workerName)
  switch (error.code) {
    case 'worker_not_confirmed':
      return timeOption
        ? `${who} has not confirmed this time yet. Wait for their reply before approving.`
        : `${who} has not confirmed this yet. Ask them first, then approve after they reply Yes.`
    case 'invalid_transition':
      return 'This case has already moved on (it was decided or handed over). The list has been refreshed.'
    case 'not_assigned':
      return 'This case is not assigned to you, so you cannot act on it.'
    case 'supervisor_only':
      return 'Only a supervisor or the payroll admin can do this.'
    case 'unknown_actor':
      return 'Your user ID is not recognised.'
    case 'invalid_params':
    case 'validation_error': {
      const why = detailText(error.details)
      return `Some values are not valid${why ? `: ${why}` : '.'}`
    }
    case 'stale_fix':
      return 'The data changed since this fix was suggested. Run detection again before deciding.'
    case 'no_fix_options':
      return 'This case has no fix options. It can only be rejected.'
    case 'exception_not_found':
      return 'This case no longer exists.'
    case 'no_reply_not_escalated':
      return `You can decide without ${who} only after they missed the reply deadline.`
    case 'reason_required':
      return `Give a reason of at least ${MIN_WITHOUT_REASON} characters for deciding without ${who}.`
    case 'time_confirmation_required':
      return `Tick "I'm confirming this time without the worker's reply" first.`
    default:
      return error.message
  }
}

/** Phase 13: "worker has not replied" badge text for the queue and the admin list. */
export function noReplyBadge(noReply: NoReply | null | undefined): string {
  if (!noReply) return ''
  if (noReply.stage === 0) return 'replied late'
  return noReply.hours_without_reply ? `no reply · ${noReply.hours_without_reply}` : 'no reply'
}

function findingText(item: Finding) {
  const when = ['P5', 'P16'].includes(item.policy_id) ? `week of ${item.date}` : item.date
  return `${item.policy_id}${item.kind ? ` ${item.kind}` : ''} (${when}): ${item.reason}`
}

// ---------------------------------------------------------------- edit form

function inputType(kind: string) {
  return kind === 'datetime' ? 'datetime-local' : kind === 'fixed' ? 'text' : kind
}

function initialValue(kind: string, value: unknown) {
  if (value === null || value === undefined) return ''
  const text = String(value)
  return kind === 'datetime' ? text.slice(0, 16) : kind === 'time' ? text.slice(0, 5) : text
}

function EditForm({
  option,
  busy,
  onSubmit,
  onCancel,
}: {
  option: CaseOption
  busy: boolean
  onSubmit: (params: Record<string, unknown>, reason: string) => void
  onCancel: () => void
}) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(
    option.fields.map((field) => [field.name, initialValue(field.kind, field.value)]),
  ))
  const [punches, setPunches] = useState<Record<string, string>>(() => Object.fromEntries(
    (option.punches ?? []).map((punch) => [punch.punch_id, initialValue('datetime', punch.timestamp)]),
  ))
  const [reason, setReason] = useState('')
  const [problem, setProblem] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    const params: Record<string, unknown> = {}
    for (const field of option.fields) {
      if (!field.editable) continue
      const value = values[field.name] ?? ''
      if (value === initialValue(field.kind, field.value)) continue
      if (value === '') {
        setProblem(`${field.name.replace(/_/g, ' ')} cannot be empty.`)
        return
      }
      params[field.name] = field.kind === 'number' ? Number(value) : value
    }
    if (option.punches) {
      const changes = option.punches
        .filter((punch) => punches[punch.punch_id] && punches[punch.punch_id] !== initialValue('datetime', punch.timestamp))
        .map((punch) => ({ punch_id: punch.punch_id, timestamp: punches[punch.punch_id] }))
      if (changes.length) params.changes = changes
    }
    if (Object.keys(params).length === 0) {
      setProblem('Change at least one value, or use Approve to keep the suggested values.')
      return
    }
    if (reason.trim().length < MIN_EDIT_REASON) {
      setProblem(`Give a reason of at least ${MIN_EDIT_REASON} characters.`)
      return
    }
    setProblem('')
    onSubmit(params, reason.trim())
  }

  return (
    <form className="edit-form" aria-label="Edit the fix" onSubmit={submit} noValidate>
      <h3>Edit: {option.label}</h3>
      {option.fields.map((field) => {
        const id = `field-${option.option_id}-${field.name}`
        return (
          <div className="field" key={field.name}>
            <label htmlFor={id}>{field.name.replace(/_/g, ' ')}</label>
            {field.editable ? (
              <input
                id={id}
                type={inputType(field.kind)}
                step={field.kind === 'number' ? 'any' : undefined}
                value={values[field.name] ?? ''}
                disabled={busy}
                onChange={(event) => setValues({ ...values, [field.name]: event.target.value })}
              />
            ) : (
              <>
                <input id={id} readOnly value={typeof field.value === 'object' ? JSON.stringify(field.value) : String(field.value ?? '')} />
                {field.locked_reason && <p className="hint">{field.locked_reason}</p>}
              </>
            )}
          </div>
        )
      })}
      {option.punches && (
        <fieldset>
          <legend>New punch times</legend>
          {option.punches.map((punch) => {
            const id = `punch-${punch.punch_id}`
            return (
              <div className="field" key={punch.punch_id}>
                <label htmlFor={id}>{punch.type ?? 'punch'} ({punch.punch_id})</label>
                <input
                  id={id}
                  type="datetime-local"
                  value={punches[punch.punch_id] ?? ''}
                  disabled={busy}
                  onChange={(event) => setPunches({ ...punches, [punch.punch_id]: event.target.value })}
                />
              </div>
            )
          })}
        </fieldset>
      )}
      <div className="field">
        <label htmlFor={`edit-reason-${option.option_id}`}>Reason for the change</label>
        <textarea
          id={`edit-reason-${option.option_id}`}
          rows={2}
          value={reason}
          disabled={busy}
          onChange={(event) => setReason(event.target.value)}
        />
      </div>
      <p className="hint">Edited values are checked when you save; any new exceptions are listed after.</p>
      {problem && <p className="error" role="alert">{problem}</p>}
      <div className="actions">
        <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save and approve'}</button>
        <button type="button" className="secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------- case card

function NoReplyNote({ noReply }: { noReply: NoReply }) {
  return (
    <section aria-label="No reply" className={noReply.stage ? 'no-reply warn-box' : 'no-reply'}>
      <h3>{noReply.label}</h3>
      <p>{noReply.note}</p>
      {noReply.can_decide_without_worker && (
        <p className="hint">Ask again, decide on the evidence, or send it to payroll.</p>
      )}
    </section>
  )
}

/** The decision card. Also used by the payroll admin page for cases escalated to her. */
export function CaseCard({
  id,
  onChanged,
  onClose,
  actor = supervisorActor.id,
}: {
  id: string
  onChanged: (message: string, closeCard: boolean) => void
  onClose: () => void
  actor?: string
}) {
  const [data, setData] = useState<SupervisorCase | null>(null)
  const [loadError, setLoadError] = useState('')
  const [reload, setReload] = useState(0)
  const [choice, setChoice] = useState('')
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const [mode, setMode] = useState<Mode>('idle')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [withoutWorker, setWithoutWorker] = useState(false)
  const [withoutReason, setWithoutReason] = useState('')
  const [timeTicked, setTimeTicked] = useState(false)
  const [escalateReason, setEscalateReason] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    getCase(id, controller.signal, actor)
      .then((body) => {
        if (controller.signal.aborted) return
        setData(body)
        setChoice((current) => current || body.options[0]?.option_id || '')
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setLoadError(plainError(failure))
      })
    return () => controller.abort()
  }, [id, reload, actor])

  if (loadError) return <section className="panel case-card"><p role="alert" className="error">{loadError}</p></section>
  if (!data) return <p role="status" className="panel">Loading the case…</p>

  const worker = data.employee.name
  const option = data.options.find((item) => item.option_id === choice) ?? null
  const decided = data.status === 'resolved' || data.status === 'rejected'
  const noteTooShort = Boolean(option?.note_field) && note.trim().length < data.min_note_length
  const canEdit = Boolean(option && (option.fields.some((field) => field.editable) || option.punches?.length))
  // Phase 13: deciding without the worker is an explicit, separate choice with its own reason.
  const canDecideWithout = Boolean(data.no_reply?.can_decide_without_worker)
  const without = canDecideWithout && withoutWorker
  const timeOption = Boolean(option && TIME_ACTIONS.has(option.action))
  const withoutBlocked = without && (
    withoutReason.trim().length < MIN_WITHOUT_REASON || (timeOption && !timeTicked)
  )
  const withoutFields = without
    ? { without_worker: true, confirm_time_without_worker: timeOption && timeTicked }
    : {}

  async function act(run: () => Promise<string>, closeCard: boolean) {
    setBusy(true)
    setError('')
    try {
      const message = await run()
      setMode('idle')
      onChanged(message, closeCard)
      if (!closeCard) setReload((value) => value + 1)
    } catch (failure) {
      setError(plainError(failure, worker, Boolean(option && TIME_ACTIONS.has(option.action))))
      if (failure instanceof ApiError && ['invalid_transition', 'not_assigned'].includes(failure.code)) {
        onChanged('', false)
      }
    } finally {
      setBusy(false)
    }
  }

  function approvedMessage(result: ApproveResult) {
    const created = result.detection.new_exception_ids
    const parts = [`Approved for ${worker}: ${result.applied_fix?.label ?? 'fix applied'}.`]
    if (created.length) parts.push(`New exceptions opened: ${created.join(', ')}.`)
    if (result.detection.error) parts.push(result.detection.error)
    return parts.join(' ')
  }

  function approve() {
    if (!option) return
    void act(async () => approvedMessage(await approveCase(data!.exception_id, {
      option_id: option.option_id,
      reason: without ? withoutReason.trim() : option.note_field ? note.trim() : undefined,
      ...withoutFields,
    }, actor)), false)
  }

  function startApprove() {
    if (option?.consequence.creates_violations) setMode('confirm')
    else approve()
  }

  function submitEscalate(event: FormEvent) {
    event.preventDefault()
    if (escalateReason.trim().length < MIN_ESCALATE) {
      setError(`Give a reason of at least ${MIN_ESCALATE} characters.`)
      return
    }
    void act(async () => {
      const result = await escalateCase(data!.exception_id, { reason: escalateReason.trim() }, actor)
      return `Sent to the payroll admin (${result.assigned_to}) with your reason. Nothing was changed.`
    }, true)
  }

  function submitReject(event: FormEvent) {
    event.preventDefault()
    if (reason.trim().length < MIN_REJECT) {
      setError(`Give a reason of at least ${MIN_REJECT} characters.`)
      return
    }
    void act(async () => {
      const result = await rejectCase(data!.exception_id, { reason: reason.trim() }, actor)
      return result.status === 'escalated'
        ? `Rejected. ${worker}'s case was sent to the payroll admin (${result.assigned_to}) with your reason.`
        : `Rejected. ${worker}'s case is closed with no change.`
    }, true)
  }

  return (
    <article className="panel case-card" aria-labelledby="case-title">
      <div className="case-head">
        <div>
          <p className="eyebrow">{data.policy_id} · {data.severity} · {data.status.replace(/_/g, ' ')}</p>
          <h2 id="case-title">{worker}, {displayDate(data.date)}</h2>
        </div>
        <button className="secondary small" onClick={onClose}>Close</button>
      </div>

      <section aria-label="The issue">
        <h3>The issue</h3>
        <p>{data.summary}</p>
      </section>

      {data.no_reply && <NoReplyNote noReply={data.no_reply} />}

      <section aria-label="Policy">
        <h3>Policy {data.policy.policy_id}: {data.policy.title}</h3>
        <blockquote>{data.policy.cited_text}</blockquote>
      </section>

      {(data.confirmed_time || data.worker) && (
        <section aria-label="What the worker said">
          <h3>What {firstName(worker)} said</h3>
          {data.confirmed_time && (
            <p>
              Confirmed time: <strong>{stampText(data.confirmed_time.timestamp)}</strong>
              {data.confirmed_time.approximate && <span className="badge warn">approximate</span>}
            </p>
          )}
          {data.worker?.reply_text ? (
            <blockquote className="quote">“{data.worker.reply_text}”</blockquote>
          ) : data.worker?.confirmed ? (
            <p>Answered Yes to the question.</p>
          ) : data.worker && !data.worker.replied ? (
            <p>No reply yet.</p>
          ) : null}
        </section>
      )}

      {data.recheck && (
        <section aria-label="Re-check">
          <h3>Re-check of the confirmed time</h3>
          <ul className="facts">
            {data.recheck.day_worked_hours !== null && data.recheck.day_worked_hours !== undefined && (
              <li>Day worked: {data.recheck.day_worked_hours} h</li>
            )}
            <li>Week projected: {data.recheck.week_projected_hours} h (limit {data.recheck.weekly_limit_hours} h)</li>
            {data.recheck.new_violations.map((item) => (
              <li key={`n-${item.policy_id}-${item.date}`} className="warn-text">New: {findingText(item)}</li>
            ))}
            {data.recheck.resolved.map((item) => (
              <li key={`r-${item.policy_id}-${item.date}`}>Resolves: {findingText(item)}</li>
            ))}
          </ul>
        </section>
      )}

      {data.applied_fix ? (
        <section aria-label="Decision" className="notice">
          <h3>Decision recorded</h3>
          <p>{String(data.applied_fix.label ?? 'Fix applied')} (by {String(data.applied_fix.approved_by ?? '')}).</p>
        </section>
      ) : null}

      {!decided && (
        <section aria-label="Fix options">
          <h3>Choose a fix</h3>
          {data.options.length === 0 && <p>No fix options. This case can only be rejected.</p>}
          <div role="radiogroup" aria-label="Fix options" className="options">
            {data.options.map((item) => (
              <label key={item.option_id} className={`option ${item.option_id === choice ? 'chosen' : ''}`}>
                <input
                  type="radio"
                  name={`option-${data.exception_id}`}
                  value={item.option_id}
                  checked={item.option_id === choice}
                  disabled={busy}
                  onChange={() => { setChoice(item.option_id); setMode('idle'); setError('') }}
                />
                <span className="option-body">
                  <strong>{item.label}</strong>
                  <span>{item.description}</span>
                  <span className={item.consequence.creates_violations ? 'consequence warn' : 'consequence'}>
                    {item.consequence.note}
                  </span>
                  {item.requires_worker_confirmation && !item.worker_confirmed && !without && (
                    <span className="hint">Needs {firstName(worker)}'s confirmation first.</span>
                  )}
                </span>
              </label>
            ))}
          </div>

          {canDecideWithout && (
            <fieldset className="without-worker" aria-label="Decide without the worker">
              <label className="check">
                <input type="checkbox" checked={withoutWorker} disabled={busy}
                  onChange={(event) => { setWithoutWorker(event.target.checked); setError('') }} />
                Decide on the evidence without {firstName(worker)}'s reply
              </label>
              {withoutWorker && (
                <>
                  <p className="hint">
                    Silence is not a Yes. Your reason is saved in the audit log and shown to {firstName(worker)}.
                  </p>
                  <label htmlFor={`without-${data.exception_id}`}>
                    Reason (required, at least {MIN_WITHOUT_REASON} characters)
                  </label>
                  <textarea id={`without-${data.exception_id}`} rows={2} value={withoutReason}
                    disabled={busy} onChange={(event) => setWithoutReason(event.target.value)} />
                  {timeOption && (
                    <label className="check">
                      <input type="checkbox" checked={timeTicked} disabled={busy}
                        onChange={(event) => setTimeTicked(event.target.checked)} />
                      I'm confirming this time without the worker's reply
                    </label>
                  )}
                </>
              )}
            </fieldset>
          )}

          {option?.note_field && (
            <div className="field">
              <label htmlFor={`note-${data.exception_id}`}>
                {option.note_field.replace(/_/g, ' ')} (required, at least {data.min_note_length} characters)
              </label>
              <textarea
                id={`note-${data.exception_id}`}
                rows={2}
                value={note}
                disabled={busy}
                onChange={(event) => setNote(event.target.value)}
              />
            </div>
          )}

          {mode === 'confirm' && option && (
            <section className="confirm" role="alertdialog" aria-label="Confirm approval">
              <p><strong>Approving creates new exceptions.</strong> {option.consequence.note}</p>
              <ul>
                {option.consequence.new_violations.map((item) => (
                  <li key={`c-${item.policy_id}-${item.date}`}>{findingText(item)}</li>
                ))}
              </ul>
              <div className="actions">
                <button disabled={busy} onClick={approve}>{busy ? 'Approving…' : 'Approve anyway'}</button>
                <button className="secondary" disabled={busy} onClick={() => setMode('idle')}>Cancel</button>
              </div>
            </section>
          )}

          {mode === 'edit' && option && (
            <EditForm
              key={option.option_id}
              option={option}
              busy={busy}
              onCancel={() => setMode('idle')}
              onSubmit={(params, why) => void act(async () => approvedMessage(
                await editCase(data.exception_id, {
                  option_id: option.option_id,
                  params,
                  reason: without ? withoutReason.trim() || why : why,
                  ...withoutFields,
                }, actor),
              ), false)}
            />
          )}

          {mode === 'escalate' && (
            <form className="reject-form" onSubmit={submitEscalate} noValidate>
              <label htmlFor={`escalate-${data.exception_id}`}>
                Why should payroll decide? (required, at least {MIN_ESCALATE} characters)
              </label>
              <textarea id={`escalate-${data.exception_id}`} rows={2} value={escalateReason}
                disabled={busy} onChange={(event) => setEscalateReason(event.target.value)} />
              <p className="hint">The case goes to the payroll admin. No decision, no timecard changes.</p>
              <div className="actions">
                <button type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send to payroll'}</button>
                <button type="button" className="secondary" disabled={busy} onClick={() => setMode('idle')}>Cancel</button>
              </div>
            </form>
          )}

          {mode === 'reject' && (
            <form className="reject-form" onSubmit={submitReject} noValidate>
              <label htmlFor={`reject-${data.exception_id}`}>
                Why are you rejecting this? (required, at least {MIN_REJECT} characters)
              </label>
              <textarea
                id={`reject-${data.exception_id}`}
                rows={3}
                value={reason}
                disabled={busy}
                onChange={(event) => setReason(event.target.value)}
              />
              <p className="hint">
                {data.status === 'escalated'
                  ? 'Your reject is final. No timecard changes.'
                  : 'The case goes to the payroll admin with your reason. No timecard changes.'}
              </p>
              <div className="actions">
                <button type="submit" disabled={busy}>{busy ? 'Rejecting…' : 'Send reject'}</button>
                <button type="button" className="secondary" disabled={busy} onClick={() => setMode('idle')}>Cancel</button>
              </div>
            </form>
          )}

          {mode === 'idle' && (
            <div className="actions">
              <button disabled={busy || !option || (noteTooShort && !without) || withoutBlocked}
                onClick={startApprove}>
                {busy ? 'Working…' : without ? 'Approve without reply' : 'Approve'}
              </button>
              <button className="secondary" disabled={busy || !canEdit}
                title={canEdit ? undefined : 'This option has nothing to edit'}
                onClick={() => { setError(''); setMode('edit') }}>Edit</button>
              <button className="secondary danger" disabled={busy}
                onClick={() => { setError(''); setMode('reject') }}>Reject</button>
              {canDecideWithout && data.status !== 'escalated' && (
                <button className="secondary" disabled={busy}
                  onClick={() => { setError(''); setMode('escalate') }}>Send to payroll</button>
              )}
            </div>
          )}
        </section>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </article>
  )
}

// ---------------------------------------------------------------- page

export function SupervisorPage() {
  const [items, setItems] = useState<QueueItem[] | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getQueue(controller.signal)
      .then((queue) => { if (!controller.signal.aborted) { setItems(queue); setError('') } })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setError(plainError(failure))
      })
    return () => controller.abort()
  }, [refresh])

  return (
    <main className="page wide" id="main">
      <h1>Decisions</h1>
      <p className="lede">Signed in as {supervisorActor.name} ({supervisorActor.id})</p>
      {notice && <p role="status" className="notice">{notice}</p>}
      <div className="split">
        <section aria-label="Queue" className="queue">
          {error ? (
            <div className="panel">
              <p role="alert" className="error">{error}</p>
              <button onClick={() => { setError(''); setItems(null); setRefresh(refresh + 1) }}>Try again</button>
            </div>
          ) : items === null ? (
            <p role="status" className="panel">Loading cases…</p>
          ) : items.length === 0 ? (
            <p className="panel">Nothing needs your decision</p>
          ) : (
            <ul className="queue-list">
              {items.map((item) => (
                <li key={item.exception_id}>
                  <button
                    className={`queue-row ${item.exception_id === selected ? 'selected' : ''}`}
                    aria-current={item.exception_id === selected}
                    onClick={() => { setSelected(item.exception_id); setNotice('') }}
                  >
                    <span className="row-top">
                      <strong>{item.employee_name}</strong>
                      <span className={`badge ${item.severity}`}>{item.severity}</span>
                    </span>
                    <span className="row-meta">
                      {item.policy_id} · {displayDate(item.date)}{item.status === 'escalated' ? ' · escalated' : ''}
                      {item.auto_resolve_undone ? ' · auto-resolve undone' : ''}
                    </span>
                    {item.no_reply && (
                      <span className={`badge ${item.no_reply.stage ? 'warn' : 'info'} no-reply-badge`}
                        title={item.no_reply.note}>{noReplyBadge(item.no_reply)}</span>
                    )}
                    <span className="row-summary">{item.summary}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
        {selected && (
          <CaseCard
            key={selected}
            id={selected}
            onClose={() => setSelected(null)}
            onChanged={(message, closeCard) => {
              if (message) setNotice(message)
              if (closeCard) setSelected(null)
              setRefresh((value) => value + 1)
            }}
          />
        )}
      </div>
      <TeamAutoFixes
        refresh={refresh}
        onUndone={(message) => { setNotice(message); setRefresh((value) => value + 1) }}
      />
    </main>
  )
}
