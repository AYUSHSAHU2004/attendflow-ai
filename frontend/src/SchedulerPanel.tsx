import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  getSchedulerStatus,
  moveDemoClock,
  runSchedulerNow,
  sendDemoPunch,
  type PunchInput,
  type SchedulerCycle,
  type SchedulerStatus,
} from './api'
import { plainError } from './SupervisorPage'

// How often the list and the status refresh while the Simulate punch panel is open.
export const POLL_MS = 4000

const PUNCH_TYPES: { value: PunchInput['type']; label: string }[] = [
  { value: 'in', label: 'Clock in' },
  { value: 'out', label: 'Clock out' },
  { value: 'break_start', label: 'Break start' },
  { value: 'break_end', label: 'Break end' },
]

function panelError(error: unknown) {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'admin_only':
        return 'Only the payroll admin can use the scheduler and the punch simulator.'
      case 'scheduler_busy':
        return 'A scheduler cycle is already running. Try again in a moment.'
      case 'punch_in_future':
      case 'punch_too_old':
      case 'duplicate_punch':
      case 'unknown_employee':
      case 'not_a_worker':
      case 'unknown_location':
        return error.message.charAt(0).toUpperCase() + error.message.slice(1) + '.'
      case 'not_found':
        return 'The demo helpers are switched off on this server (ATTENDFLOW_DEMO_MODE).'
      case 'clock_limit':
        return 'The demo clock cannot move more than 14 days past the start. Reset the demo to start again.'
    }
  }
  return plainError(error)
}

function clockTime(iso: string | null | undefined) {
  if (!iso) return ''
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleTimeString()
}

export function cycleLine(cycle: SchedulerCycle) {
  const parts = [
    `${cycle.new} new`,
    `${cycle.investigated.length} investigated`,
    `${cycle.messages_sent.length} message${cycle.messages_sent.length === 1 ? '' : 's'} sent`,
  ]
  if (cycle.skipped_budget.length) parts.push(`${cycle.skipped_budget.length} left for the next cycle`)
  if (cycle.skipped_backlog) parts.push(`${cycle.skipped_backlog} older case${cycle.skipped_backlog === 1 ? '' : 's'} left alone`)
  const ladder = cycle.no_reply
  if (ladder?.reminded?.length) parts.push(`${ladder.reminded?.length} reminder${ladder.reminded?.length === 1 ? '' : 's'} sent`)
  if (ladder?.to_supervisor?.length) parts.push(`${ladder.to_supervisor?.length} sent to the supervisor (no reply)`)
  if (ladder?.to_admin?.length) parts.push(`${ladder.to_admin?.length} sent to payroll (no reply)`)
  if (cycle.errors.length) parts.push(`${cycle.errors.length} error${cycle.errors.length === 1 ? '' : 's'}`)
  return parts.join(', ')
}

export const CLOCK_STEPS: { hours: number; label: string }[] = [
  { hours: 1, label: '+1 h' },
  { hours: 8, label: '+8 h' },
  { hours: 24, label: '+1 day' },
]

/** "Thu 16 Apr 08:00" from a plain local timestamp (no timezone maths). */
export function demoTime(iso: string) {
  const day = new Date(iso.slice(0, 10) + 'T00:00:00Z')
  const weekday = day.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' })
  const month = day.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' })
  return `${weekday} ${day.getUTCDate()} ${month} ${iso.slice(11, 16)}`
}

function StatusLine({ status }: { status: SchedulerStatus }) {
  const last = status.last_cycle
  return (
    <p className="hint scheduler-line" aria-live="polite" data-testid="scheduler-status">
      Scheduler {status.running ? `on (every ${status.interval_seconds} s)` : 'off'}
      {status.cycle_in_progress && ' · a cycle is running'}
      {' · '}
      {last
        ? <>last cycle {clockTime(last.finished_at ?? last.started_at)}: {cycleLine(last)}</>
        : 'no cycle yet'}
    </p>
  )
}

/** Scheduler status and "Run scheduler now" for Priya, plus the DEMO_MODE-only Simulate
 *  punch form. `onChanged` refreshes the exceptions table and counters. */
export function SchedulerPanel({ onChanged, pollMs = POLL_MS }: { onChanged: () => void; pollMs?: number }) {
  const [status, setStatus] = useState<SchedulerStatus | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [open, setOpen] = useState(true)
  const [running, setRunning] = useState(false)
  const [sending, setSending] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [moving, setMoving] = useState(false)
  const [form, setForm] = useState({ employee_id: '', type: 'in' as PunchInput['type'], date: '', time: '' })
  const changed = useRef(onChanged)
  changed.current = onChanged

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const body = await getSchedulerStatus(signal)
      if (signal?.aborted) return
      setStatus(body)
      setLoadError(null)
      // Default the form to the first worker and the demo clock's "now".
      setForm((current) => current.employee_id ? current : {
        ...current,
        employee_id: body.workers[0]?.employee_id ?? '',
        date: body.clock.data_as_of.slice(0, 10),
        time: body.clock.data_as_of.slice(11, 16),
      })
    } catch (failure) {
      if (!signal?.aborted) setLoadError(failure)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  const demo = Boolean(status?.demo_mode)
  // While the demo panel is open, the list and the status refresh on their own.
  useEffect(() => {
    if (!demo || !open) return
    const timer = setInterval(() => {
      void load()
      changed.current()
    }, pollMs)
    return () => clearInterval(timer)
  }, [demo, open, load, pollMs])

  async function runNow() {
    setRunning(true)
    setNotice('')
    setError('')
    try {
      const cycle = await runSchedulerNow()
      setNotice(`Cycle ${cycle.cycle_id} done: ${cycleLine(cycle)}.`)
    } catch (failure) {
      setError(panelError(failure))
    } finally {
      setRunning(false)
      void load()
      changed.current()
    }
  }

  async function moveClock(hours: number) {
    setMoving(true)
    setNotice('')
    setError('')
    try {
      const clock = await moveDemoClock(hours)
      setNotice(`Demo clock is now ${demoTime(clock.now)}. ${clock.hint ?? ''}`.trim())
    } catch (failure) {
      setError(panelError(failure))
    } finally {
      setMoving(false)
      void load()
    }
  }

  async function send(event: React.FormEvent) {
    event.preventDefault()
    if (!form.employee_id || !form.date || !form.time) {
      setError('Pick a worker, a date and a time.')
      return
    }
    setSending(true)
    setNotice('')
    setError('')
    try {
      const result = await sendDemoPunch({
        employee_id: form.employee_id,
        type: form.type,
        timestamp: `${form.date}T${form.time}`,
        source: 'device',
      })
      const found = result.detection.new_exception_ids
      const closed = result.detection.closed_exception_ids
      setNotice(
        `Punch ${result.punch.punch_id} stored. ` +
        (found.length ? `New: ${found.join(', ')}. ` : 'No new exception. ') +
        (closed.length ? `Closed: ${closed.join(', ')}.` : '') +
        (result.detection.error ? ` ${result.detection.error}` : ''),
      )
      changed.current()
    } catch (failure) {
      setError(panelError(failure))
    } finally {
      setSending(false)
    }
  }

  if (loadError) {
    // The page itself already explains a 403; only other failures are shown here.
    if (loadError instanceof ApiError && loadError.code === 'admin_only') return null
    return (
      <section className="panel scheduler-panel" aria-label="Scheduler">
        <p className="error">Scheduler status unavailable: {panelError(loadError)}</p>
        <button className="secondary small" onClick={() => void load()}>Try again</button>
      </section>
    )
  }
  if (!status) return <p className="hint scheduler-line">Loading the scheduler status…</p>

  return (
    <section className="panel scheduler-panel" aria-label="Scheduler">
      <div className="scheduler-head">
        <StatusLine status={status} />
        <div className="scheduler-buttons">
          <button className="small" onClick={() => void runNow()} disabled={running}>
            {running ? 'Running…' : 'Run scheduler now'}
          </button>
          {demo && (
            <button className="secondary small" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
              {open ? 'Hide punch simulator' : 'Simulate punch'}
            </button>
          )}
        </div>
      </div>
      {running && <p className="hint">Detecting, investigating new cases, messaging workers and checking for no replies…</p>}

      <div className="demo-clock" aria-label="Demo clock">
        <p className="hint">
          Clock: <strong data-testid="demo-now">{demoTime(status.clock.now)}</strong>
          {status.clock.offset_hours > 0 && ` (+${status.clock.offset_hours} h)`}
          {' · '}data as of {demoTime(status.clock.data_as_of)}
          {status.no_reply.enabled
            ? ` · no reply: reminder ${status.no_reply.reminder_hours} h, supervisor ${status.no_reply.supervisor_hours} h, payroll +${status.no_reply.admin_hours} h`
            : ' · no-reply steps off'}
        </p>
        {status.clock.movable && (
          <div className="scheduler-buttons" role="group" aria-label="Move the demo clock">
            {CLOCK_STEPS.map((step) => (
              <button key={step.hours} className="secondary small" disabled={moving}
                onClick={() => void moveClock(step.hours)}
                aria-label={`Move the demo clock ${step.label}`}>{step.label}</button>
            ))}
          </div>
        )}
      </div>

      {demo && open && (
        <form className="filters punch-form" aria-label="Simulate punch" onSubmit={(event) => void send(event)}>
          <label>
            Worker
            <select value={form.employee_id} onChange={(event) => setForm({ ...form, employee_id: event.target.value })}>
              {status.workers.map((w) => (
                <option key={w.employee_id} value={w.employee_id}>{w.name} ({w.employee_id})</option>
              ))}
            </select>
          </label>
          <label>
            Punch
            <select value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value as PunchInput['type'] })}>
              {PUNCH_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </label>
          <label>
            Date
            <input type="date" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} />
          </label>
          <label>
            Time
            <input type="time" value={form.time} onChange={(event) => setForm({ ...form, time: event.target.value })} />
          </label>
          <button type="submit" disabled={sending}>{sending ? 'Sending…' : 'Send'}</button>
          <p className="hint block">
            Demo only. Punches after {status.clock.data_as_of.slice(0, 16).replace('T', ' ')} (the data cut-off) are refused.
            The list refreshes every {Math.round(pollMs / 1000)} s while this panel is open.
          </p>
        </form>
      )}
      {notice && <p className="notice" aria-live="polite">{notice}</p>}
      {error && <p className="error" aria-live="assertive">{error}</p>}
    </section>
  )
}
