import { useEffect, useState, type ReactNode } from 'react'
import { dashboardActor, supervisorDashboardPath } from './actors'
import { adminListHref, getDashboard, type AdminFilters, type Dashboard, type DashboardFilters } from './api'
import { AutoResolveSummary } from './AutoFix'
import { plainError } from './SupervisorPage'

const statuses = {
  open: 'Open',
  awaiting_worker: 'Waiting for worker',
  awaiting_supervisor: 'Waiting for supervisor',
  escalated: 'Escalated',
} as const

const ladder = {
  waiting: 'Waiting for first reminder',
  reminded: 'Reminder sent',
  supervisor: 'With supervisor',
  payroll_admin: 'With Priya',
} as const

const riskLabels = {
  approaching: 'Approaching limit',
  at_limit: 'At limit',
  projected_over: 'Projected over',
  already_over: 'Already over',
}

type Bar = { label: string; count: number; href?: string }
type CaseLink = (filters: AdminFilters) => string | undefined

function Bars({ rows }: { rows: Bar[] }) {
  const max = Math.max(1, ...rows.map((row) => row.count))
  return (
    <ul className="dashboard-bars">
      {rows.map(({ label, count, href }) => (
        <li key={label}>
          {href && count > 0 ? <a href={href}>{label}</a> : <span>{label}</span>}
          <strong>{count}</strong>
          <span className="dashboard-bar-track" aria-hidden="true">
            <span style={{ width: `${100 * count / max}%` }} />
          </span>
        </li>
      ))}
    </ul>
  )
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel dashboard-panel" aria-label={title}>
      <h2>{title}</h2>
      {children}
    </section>
  )
}

function AgeBars({ limits, counts }: { limits: number[]; counts: number[] }) {
  const labels = limits.map((limit, index) =>
    index === 0 ? `Under ${limit} h` : `${limits[index - 1]} to under ${limit} h`,
  )
  labels.push(`${limits.at(-1)} h or more`)
  return <Bars rows={labels.map((label, index) => ({ label, count: counts[index] ?? 0 }))} />
}

function CountLink({ href, count }: { href?: string; count: number }) {
  return href && count > 0 ? <a href={href}>{count}</a> : count
}

function Workload({ rows, caseLink }: { rows: Dashboard['workload']; caseLink: CaseLink }) {
  if (rows.length === 0) return <p>No teams have cases or workers to show.</p>
  return (
    <table className="dashboard-table">
      <thead><tr><th scope="col">Supervisor</th><th scope="col">Active</th>
        <th scope="col">Waiting for worker</th><th scope="col">Waiting for supervisor</th>
      </tr></thead>
      <tbody>{rows.map((row) => {
        const teamLink = (filters: AdminFilters) => row.supervisor_id
          ? caseLink({ ...filters, supervisor_id: row.supervisor_id })
          : undefined
        return (
          <tr key={row.supervisor_id ?? 'unassigned'}>
            <th scope="row">{row.supervisor_name}</th>
            <td><CountLink count={row.active} href={teamLink({ active_only: true })} /></td>
            <td><CountLink count={row.awaiting_worker} href={teamLink({ status: 'awaiting_worker' })} /></td>
            <td><CountLink count={row.awaiting_supervisor} href={teamLink({ status: 'awaiting_supervisor' })} /></td>
          </tr>
        )
      })}</tbody>
    </table>
  )
}

function Overtime({ data, caseLink }: { data: Dashboard['overtime']; caseLink: CaseLink }) {
  return (
    <>
      <p>{data.week_start} to {data.week_end} · {data.limit_hours} h limit · {data.warning_margin_hours} h warning margin</p>
      {data.workers.length === 0 ? <p>No workers are near or above the limit.</p> : (
        <table className="dashboard-table">
          <thead><tr><th scope="col">Worker</th><th scope="col">Worked</th>
            <th scope="col">Scheduled</th><th scope="col">Projected</th>
          </tr></thead>
          <tbody>{data.workers.map((row) => {
            const href = row.level.endsWith('_over') ? caseLink({
              policy_id: 'P5', employee_id: row.employee_id,
              date_from: data.week_start, date_to: data.week_end,
            }) : undefined
            return (
              <tr key={row.employee_id}>
                <th scope="row">
                  {row.employee_name}
                  <span className="dashboard-risk">{riskLabels[row.level]}</span>
                  {href && <a href={href} aria-label={`P5 cases for ${row.employee_name}`}>P5 cases</a>}
                </th>
                <td>{row.worked_hours} h</td><td>{row.scheduled_remaining_hours} h</td>
                <td><strong>{row.projected_hours} h</strong></td>
              </tr>
            )
          })}</tbody>
        </table>
      )}
      <p className="hint">Worked hours may include estimates for missing punches. The forecast always covers the week at the attendance data cutoff.</p>
    </>
  )
}

function DashboardPanels({ data, dates }: { data: Dashboard; dates: DashboardFilters }) {
  const caseLink: CaseLink = (filters) => data.scope === 'all'
    ? adminListHref({ ...dates, ...filters })
    : undefined
  const positions = Object.keys(statuses) as (keyof typeof statuses)[]
  const steps = Object.keys(ladder) as (keyof typeof ladder)[]
  const stuckLink = caseLink({ no_reply: 'any' })
  const metricLink = caseLink({ auto_resolved: true })
  return (
    <>
      <p className="dashboard-timestamp">As of {data.workflow_now.slice(0, 16).replace('T', ' ')}</p>
      {data.active_total === 0 && <p className="panel">No active exceptions in this date range.</p>}
      <div className="dashboard-grid">
        <Panel title="Open work">
          <p><strong>{data.active_total}</strong> active ·{' '}
            {stuckLink && data.stuck > 0 ? <a href={stuckLink}>{data.stuck} stuck on no reply</a>
              : <>{data.stuck} stuck on no reply</>}
          </p>
          <h3>By severity</h3>
          <Bars rows={(['high', 'medium', 'low'] as const).map((severity) => ({
            label: severity[0].toUpperCase() + severity.slice(1),
            count: data.by_severity[severity] ?? 0,
            href: caseLink({ severity, active_only: true }),
          }))} />
          <h3>By status</h3>
          <Bars rows={positions.map((status) => ({
            label: statuses[status], count: data.by_status[status] ?? 0, href: caseLink({ status }),
          }))} />
          <h3>No-reply stages</h3>
          <Bars rows={steps.map((no_reply) => ({
            label: ladder[no_reply], count: data.ladder[no_reply] ?? 0,
            href: caseLink({ no_reply, active_only: true }),
          }))} />
        </Panel>
        <Panel title="Open work by policy">
          {Object.keys(data.by_policy).length === 0 ? <p>No active policy exceptions.</p> : (
            <Bars rows={Object.entries(data.by_policy).map(([policy_id, count]) => ({
              label: policy_id, count, href: caseLink({ policy_id, active_only: true }),
            }))} />
          )}
        </Panel>
        <Panel title="Case aging">
          <h3>Since first detected</h3>
          <AgeBars limits={data.aging.limits_hours} counts={data.aging.case_age} />
          <h3>In current waiting status</h3>
          <AgeBars limits={data.aging.limits_hours} counts={data.aging.waiting_age} />
        </Panel>
        <Panel title="Team workload"><Workload rows={data.workload} caseLink={caseLink} /></Panel>
        <Panel title="Weekly overtime risk"><Overtime data={data.overtime} caseLink={caseLink} /></Panel>
        <div className="dashboard-metric">
          <AutoResolveSummary metric={data.auto_resolve} />
          {metricLink && data.auto_resolve.resolved_without_human > 0 && (
            <a href={metricLink}>View auto-resolved cases</a>
          )}
        </div>
      </div>
    </>
  )
}

export function DashboardPage() {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [dates, setDates] = useState<DashboardFilters>({})
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getDashboard(dates, dashboardActor.id, controller.signal)
      .then((body) => { if (!controller.signal.aborted) setData(body) })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(plainError(failure)) })
    return () => controller.abort()
  }, [dates, refresh])

  function applyDates(next: DashboardFilters) {
    setError('')
    setData(null)
    setDates(next)
  }

  const supervisorHref = import.meta.env.DEV ? `/supervisor?as=${dashboardActor.id}` : '/supervisor'
  const team = data?.scope === 'team' || (
    data === null && typeof window !== 'undefined' && window.location.pathname === supervisorDashboardPath
  )
  return (
    <main className="page wide dashboard" id="main">
      <h1>Operations dashboard</h1>
      <p className="lede">{dashboardActor.name} · {team
        ? <>Your team · <a href={supervisorHref}>Decision queue</a></>
        : <>All teams · <a href="/admin">All exceptions</a></>}
      </p>
      <form className="filters" aria-label="Exception dates" onSubmit={(event) => {
        event.preventDefault()
        applyDates({ date_from: from || undefined, date_to: to || undefined })
      }}>
        <label>From<input type="date" value={from} onChange={(event) => setFrom(event.target.value)} /></label>
        <label>To<input type="date" value={to} min={from || undefined} onChange={(event) => setTo(event.target.value)} /></label>
        <button type="submit">Apply dates</button>
        <button type="button" className="secondary" disabled={!from && !to} onClick={() => {
          setFrom('')
          setTo('')
          applyDates({})
        }}>Clear dates</button>
      </form>
      {error ? (
        <div className="panel">
          <p role="alert" className="error">{error}</p>
          <button type="button" onClick={() => { setError(''); setRefresh((value) => value + 1) }}>Try again</button>
        </div>
      ) : data ? <DashboardPanels data={data} dates={dates} />
        : <p role="status" className="panel">Loading operations dashboard…</p>}
    </main>
  )
}
