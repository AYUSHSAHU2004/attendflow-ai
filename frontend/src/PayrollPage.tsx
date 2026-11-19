import { useEffect, useState } from 'react'
import { payrollActor } from './actors'
import { ApiError, getPayroll, reopenPayroll, signPayroll } from './api'
import type { PayrollReadiness, ReadinessReason } from './api'

const statusLabel = {
  ready: 'Ready',
  ready_with_notes: 'Ready with notes',
  blocked: 'Blocked',
}
const contactLabel = { worker: 'worker', supervisor: 'supervisor', hr: 'payroll' }

function problem(error: unknown) {
  return error instanceof ApiError ? error.message : 'The server could not be reached.'
}

function ReasonList({ reasons, team, names }: {
  reasons: ReadinessReason[]
  team: boolean
  names?: Map<string, string>
}) {
  if (!reasons.length) return <span>None</span>
  const caseHref = (id: string) => {
    const path = team ? '/supervisor' : '/admin'
    const actor = team && import.meta.env.DEV ? '&as=' + payrollActor.id : ''
    return path + '?case=' + encodeURIComponent(id) + actor
  }
  return <ul className="payroll-reasons">
    {reasons.map((reason, index) => <li key={index}>
      {names && <strong>{names.get(reason.employee_id)} · </strong>}
      {reason.blocking ? 'Blocker' : 'Note'} · {reason.message}
      {reason.owner_name && <span> · Next: {reason.owner_name}</span>}
      {reason.contact && reason.owner_id !== reason.employee_id &&
        <span> · Contact: {contactLabel[reason.contact]}</span>}
      {reason.exception_ids.map((id) => <span key={id}> · <a href={caseHref(id)}>{id}</a></span>)}
    </li>)}
  </ul>
}

function ReadinessTables({ report }: { report: PayrollReadiness }) {
  const team = report.scope === 'team'
  const names = new Map(report.workers.map((worker) => [worker.employee_id, worker.employee_name]))
  return <>
    <section className="panel">
      <h2>Teams</h2>
      <table className="payroll-table">
        <thead><tr><th scope="col">Team</th><th scope="col">Status</th><th scope="col">Reasons</th></tr></thead>
        <tbody>{report.teams.map((row) => <tr key={row.team}>
          <th scope="row">{row.team}</th><td>{statusLabel[row.status]}</td>
          <td><ReasonList reasons={row.reasons} team={team} names={names} /></td>
        </tr>)}</tbody>
      </table>
    </section>
    <section className="panel">
      <h2>Workers</h2>
      <table className="payroll-table">
        <thead><tr><th scope="col">Worker</th><th scope="col">Status</th><th scope="col">Reasons</th></tr></thead>
        <tbody>{report.workers.map((row) => <tr key={row.employee_id}>
          <th scope="row">{row.employee_name} <small>{row.team}</small></th>
          <td>{statusLabel[row.status]}</td>
          <td><ReasonList reasons={row.reasons} team={team} /></td>
        </tr>)}</tbody>
      </table>
    </section>
  </>
}

export function PayrollPage() {
  const [week, setWeek] = useState('')
  const [draftWeek, setDraftWeek] = useState('')
  const [report, setReport] = useState<PayrollReadiness | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [action, setAction] = useState<'sign' | 'reopen' | null>(null)
  const [note, setNote] = useState('')
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    getPayroll(week, payrollActor.id, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setReport(data)
        setDraftWeek(data.week_start)
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setError(problem(failure))
      })
    return () => controller.abort()
  }, [week, refresh])

  function selectWeek(next: string) {
    setReport(null)
    setError('')
    setAction(null)
    setActionError('')
    setNote('')
    setWeek(next)
    setRefresh((value) => value + 1)
  }

  async function confirm() {
    if (!report || !action || pending) return
    setPending(true)
    setActionError('')
    try {
      const update = action === 'sign' ? signPayroll : reopenPayroll
      setReport(await update(report.week_start, payrollActor.id, note))
      setAction(null)
      setNote('')
    } catch (failure) {
      setActionError(problem(failure))
    } finally {
      setPending(false)
    }
  }

  const names = new Map(report?.workers.map((row) => [row.employee_id, row.employee_name]))
  return <main className="page wide payroll" id="main">
    <h1>Payroll readiness</h1>
    <form className="filters" aria-label="Pay period" onSubmit={(event) => {
      event.preventDefault()
      selectWeek(draftWeek)
    }}>
      <label>Week starting Monday<input type="date" value={draftWeek}
        onChange={(event) => setDraftWeek(event.target.value)} required /></label>
      <button disabled={pending}>View week</button>
      <button type="button" className="secondary" disabled={pending} onClick={() => selectWeek('')}>
        Current week
      </button>
    </form>
    {error ? <section className="panel">
      <p role="alert" className="error">{error}</p>
      <button onClick={() => selectWeek(week)}>Try again</button>
    </section> : report ? <>
      <section className="panel" aria-labelledby="readiness-status">
        <h2 id="readiness-status">{report.has_data ? statusLabel[report.status] : 'No attendance data'}</h2>
        <p>{report.week_start} to {report.week_end} · {report.scope === 'team' ? 'Your team' : 'All teams'}</p>
        {!report.closed && <p>In progress · sign-off unavailable. Evaluated through {report.data_cutoff.replace('T', ' ')}.</p>}
        {report.reasons.length > 0 && <ReasonList reasons={report.reasons} team={report.scope === 'team'} names={names} />}
        {report.signoff && <p role="status">
          {report.signoff.reopened_at ? 'Reopened' : report.signoff.stale ? 'Sign-off out of date' : 'Signed off'}
          {' · '}{report.signoff.signer_name} · {report.signoff.signed_at.replace('T', ' ')}
          {report.signoff.note && <> · {report.signoff.note}</>}
          {report.signoff.reopened_at && <> · Reopened {report.signoff.reopened_at.replace('T', ' ')}</>}
        </p>}
        {action ? <form className="payroll-confirm" onSubmit={(event) => {
          event.preventDefault()
          void confirm()
        }}>
          <label>{action === 'sign' ? 'Sign-off note (optional)' : 'Reason to reopen'}
            <textarea value={note} onChange={(event) => setNote(event.target.value)}
              maxLength={500} required={action === 'reopen'} disabled={pending} />
          </label>
          <div className="actions">
            <button disabled={pending || (action === 'reopen' && note.trim().length < 10)}>
              {action === 'sign' ? 'Confirm sign-off' : 'Confirm reopen'}
            </button>
            <button type="button" className="secondary" disabled={pending}
              onClick={() => { setAction(null); setActionError(''); setNote('') }}>Cancel</button>
          </div>
          {actionError && <p role="alert" className="error">{actionError}</p>}
        </form> : <>
          {report.can_sign && <button onClick={() => setAction('sign')}>Sign off week</button>}
          {report.can_reopen && <button onClick={() => setAction('reopen')}>Reopen week</button>}
        </>}
      </section>
      {report.has_data && <ReadinessTables report={report} />}
    </> : <p role="status" className="panel">Loading payroll readiness…</p>}
  </main>
}
