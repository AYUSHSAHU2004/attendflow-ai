import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminPage } from './AdminPage'
import {
  ApiError,
  getAdminCase,
  getAdminOverview,
  getCase,
  getAutoResolveMetric,
  getSchedulerStatus,
  pollInvestigation,
  startInvestigation,
  type AdminCase,
  type AdminItem,
  type AdminOverview,
} from './api'

vi.mock('./api', async (importOriginal) => ({
  ...await importOriginal<typeof import('./api')>(),
  getAdminOverview: vi.fn(),
  getAdminCase: vi.fn(),
  startInvestigation: vi.fn(),
  pollInvestigation: vi.fn(),
  getCase: vi.fn(),
  getSchedulerStatus: vi.fn(),
  getAutoResolveMetric: vi.fn(),
  undoAutoResolve: vi.fn(),
}))
import { metric, schedulerStatus } from './testFixtures'

const AMIT_P1 = 'P1-E001-2026-04-14'
const MEENA_P5 = 'P5-E002-2026-04-13'

function item(overrides: Partial<AdminItem> = {}): AdminItem {
  return {
    exception_id: AMIT_P1,
    employee_id: 'E001',
    employee_name: 'Amit Verma',
    team: 'Inbound',
    date: '2026-04-14',
    policy_id: 'P1',
    title: 'Every shift needs a clock-in and a clock-out',
    summary: 'Clock-in 09:00, no clock-out',
    severity: 'high',
    kind: 'breach',
    status: 'open',
    auto_resolved: false,
    auto_resolve_undone: false,
    assigned_to: 'E101',
    assigned_to_name: 'Ravi Kumar',
    investigated: false,
    who_to_ask: null,
    investigation_fallback: null,
    needs_your_decision: false,
    updated_at: '2026-04-16T08:00:00',
    ...overrides,
  }
}

const meena = item({
  exception_id: MEENA_P5, employee_id: 'E002', employee_name: 'Meena Iyer', date: '2026-04-13',
  policy_id: 'P5', kind: 'risk', severity: 'medium', status: 'escalated', assigned_to: 'E201',
  assigned_to_name: 'Priya Sharma', investigated: true, who_to_ask: 'supervisor',
  investigation_fallback: true, needs_your_decision: true,
})

function overview(items: AdminItem[] = [item(), meena]): AdminOverview {
  return {
    counters: {
      total: 17, open: 14, awaiting_worker: 0, awaiting_supervisor: 0, escalated: 1,
      resolved: 2, rejected: 0, auto_resolved: 2, stuck: 0,
    },
    matched: items.length,
    limit: 200,
    offset: 0,
    items,
    filter_options: {
      statuses: ['open', 'awaiting_worker', 'awaiting_supervisor', 'escalated', 'resolved', 'rejected'],
      policy_ids: ['P1', 'P5'],
      teams: ['Inbound', 'Outbound'],
      employees: [
        { employee_id: 'E001', name: 'Amit Verma', team: 'Inbound' },
        { employee_id: 'E002', name: 'Meena Iyer', team: 'Inbound' },
      ],
      severities: ['high', 'medium', 'low'],
    },
  }
}

function makeCase(overrides: Partial<AdminCase> = {}): AdminCase {
  return {
    exception_id: AMIT_P1,
    status: 'open',
    assigned_to: 'E101',
    assigned_to_name: 'Ravi Kumar',
    needs_your_decision: false,
    can_investigate: true,
    auto_resolved: false,
    employee: { employee_id: 'E001', name: 'Amit Verma', team: 'Inbound' },
    date: '2026-04-14',
    policy_id: 'P1',
    title: 'Every shift needs a clock-in and a clock-out',
    summary: 'Clock-in 09:00, no clock-out (scheduled end 18:00)',
    severity: 'high',
    kind: 'breach',
    details: {},
    policy: { policy_id: 'P1', title: 'Missing punch', rule: 'Every shift needs both.', cited_text: 'Every shift needs both.' },
    evidence: [{ punch_id: 'P0037', type: 'in', timestamp: '2026-04-14T09:00:00' }],
    options: [],
    investigation: null,
    latest_job: null,
    worker_messages: [],
    recheck: null,
    applied_fix: null,
    audit_trail: [
      {
        id: 1, created_at: '2026-04-16T08:00:00', actor: 'system', actor_id: null, actor_name: null,
        action: 'detected', summary: 'Found by the rule engine.', reason: null,
        before_summary: null, after_summary: 'open, with Ravi Kumar',
      },
    ],
    tool_calls: [],
    ...overrides,
  }
}

beforeEach(() => {
  vi.mocked(getAdminOverview).mockReset().mockResolvedValue(overview())
  vi.mocked(getAdminCase).mockReset().mockResolvedValue(makeCase())
  vi.mocked(startInvestigation).mockReset()
  vi.mocked(pollInvestigation).mockReset()
  vi.mocked(getCase).mockReset()
  vi.mocked(getSchedulerStatus).mockReset().mockResolvedValue(schedulerStatus())
  vi.mocked(getAutoResolveMetric).mockReset().mockResolvedValue(metric())
})

describe('AdminPage', () => {
  it('opens a dashboard drill-down with the active, severity and date filters', async () => {
    const original = window.location.href
    window.history.replaceState(null, '', '/admin?active_only=true&severity=high&date_from=2026-04-14')
    try {
      render(<AdminPage />)
      await screen.findByRole('region', { name: 'Counters' })
      expect(getAdminOverview).toHaveBeenLastCalledWith(
        { active_only: true, severity: 'high', date_from: '2026-04-14' }, expect.anything(),
      )
      expect(screen.getByText('Active cases · Severity: high · From 2026-04-14')).toBeVisible()
    } finally {
      window.history.replaceState(null, '', original)
    }
  })

  it('shows the counters and every exception', async () => {
    render(<AdminPage />)
    const counters = await screen.findByRole('region', { name: 'Counters' })
    expect(within(counters).getByRole('button', { name: 'All: 17' })).toBeVisible()
    expect(within(counters).getByRole('button', { name: 'Escalated: 1' })).toBeVisible()
    expect(within(counters).getByRole('button', { name: 'Auto-resolved: 2' })).toBeDisabled()
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(within(rows[1]).getByText('Needs your decision')).toBeVisible()
    expect(within(rows[0]).queryByText('Needs your decision')).toBeNull()
    expect(screen.getByText('Showing 2 of 2')).toBeVisible()
  })

  it('sends filters, the debounced name search and counter clicks to the API', async () => {
    const user = userEvent.setup()
    render(<AdminPage />)
    await screen.findByRole('region', { name: 'Counters' })
    expect(getAdminOverview).toHaveBeenCalledTimes(1)
    expect(getAdminOverview).toHaveBeenLastCalledWith({}, expect.anything())

    await user.selectOptions(screen.getByLabelText('Status'), 'escalated')
    await waitFor(() => expect(getAdminOverview).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'escalated' }), expect.anything()))
    await user.selectOptions(screen.getByLabelText('Policy'), 'P5')
    await user.selectOptions(screen.getByLabelText('Team'), 'Inbound')
    await user.selectOptions(screen.getByLabelText('Employee'), 'E002')
    await waitFor(() => expect(getAdminOverview).toHaveBeenLastCalledWith(
      { status: 'escalated', policy_id: 'P5', team: 'Inbound', employee_id: 'E002' },
      expect.anything()))

    await user.type(screen.getByLabelText('Search'), 'meena')
    await waitFor(() => expect(getAdminOverview).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: 'meena' }), expect.anything()))

    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(getAdminOverview).toHaveBeenLastCalledWith({}, expect.anything()))

    await user.click(screen.getByRole('button', { name: 'Open: 14' }))
    await waitFor(() => expect(getAdminOverview).toHaveBeenLastCalledWith({ status: 'open' }, expect.anything()))
  })

  it('says so when nothing matches', async () => {
    vi.mocked(getAdminOverview).mockResolvedValue(overview([]))
    render(<AdminPage />)
    expect(await screen.findByText('No exceptions match these filters.')).toBeVisible()
  })

  it('explains a refusal and can try again', async () => {
    const user = userEvent.setup()
    vi.mocked(getAdminOverview).mockRejectedValueOnce(
      new ApiError(403, 'admin_only', 'only the payroll admin can open the admin view'),
    )
    render(<AdminPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Only the payroll admin can open this page.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('region', { name: 'Counters' })).toBeVisible()
  })

  it('shows a loading state first', () => {
    vi.mocked(getAdminOverview).mockReturnValue(new Promise(() => {}))
    render(<AdminPage />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading exceptions')
  })
})

describe('AdminDetail', () => {
  it('opens a read-only detail with the reply, re-check, options and audit trail', async () => {
    const user = userEvent.setup()
    vi.mocked(getAdminCase).mockResolvedValue(makeCase({
      status: 'resolved',
      can_investigate: false,
      investigation: {
        what_happened: 'Clock-in 09:00, no clock-out.', policy_id: 'P1', policy_text_cited: 'Every shift needs both.',
        evidence: [{ fact: 'Scheduled 09:00 to 18:00.', source: 'get_schedule' }],
        proposed_fix: { option_id: 'set_clock_out_to_scheduled_end', params: {} },
        validation_result: null, who_to_ask: 'worker', confidence: 'low', fallback: true,
        tool_steps: 0, duration_ms: 1, next_action: 'Ask the worker',
      },
      worker_messages: [{
        id: 1, sent_at: '2026-04-16T08:00:00', source: 'template', message: 'Did you leave at 18:00?',
        reply_prompt: 'Yes or No', confirmed: false, reply_text: 'left around 7:30ish',
        replied_at: '2026-04-16T08:00:00', needs_actual_time: false, time_review: null,
      }],
      recheck: {
        timestamp: '2026-04-14T19:30:00', source: 'llm', approximate: true, proposed_fix: {},
        impact_note: 'Makes the day 9.5 h.',
        result: {
          ok: true, employee_id: 'E001', date: '2026-04-14', week_start: '2026-04-13',
          day_worked_hours: 9.5, week_projected_hours: 41.5, weekly_limit_hours: 40,
          new_violations: [], resolved: [], still_open: [],
        } as unknown as NonNullable<AdminCase['recheck']>['result'],
      },
      options: [{
        option_id: 'set_clock_out_to_scheduled_end', action: 'set_clock_out', label: 'Set clock-out to 19:30',
        description: 'Adds a correction punch.', params: {}, decision_only: false,
        requires_worker_confirmation: true, worker_confirmed: true, note_field: null, fields: [], punches: null,
        consequence: {
          source: 'worker_recheck', note: 'Approving a 19:30 clock-out makes the day 9.5 h.',
          creates_violations: true, new_violations: [], resolved: [], day_worked_hours: 9.5,
          week_projected_hours: 41.5, weekly_limit_hours: 40,
        },
      }],
      applied_fix: { label: 'Set clock-out to 19:30' },
      audit_trail: [
        makeCase().audit_trail[0],
        {
          id: 9, created_at: '2026-04-16T08:00:00', actor: 'supervisor', actor_id: 'E101',
          actor_name: 'Ravi Kumar', action: 'approve', summary: 'Approved: Set clock-out to 19:30.',
          reason: null, before_summary: 'awaiting supervisor, with Ravi Kumar',
          after_summary: 'resolved, with Ravi Kumar',
        },
      ],
      tool_calls: [{ run_id: 'r', step_no: 0, call_no: 0, tool_name: 'get_schedule', input: {}, ok: true, error_code: null, duration_ms: 3.2, result_summary: 'Scheduled 09:00 to 18:00.' }],
    }))
    render(<AdminPage />)
    await user.click(await screen.findByRole('button', { name: `Open ${AMIT_P1}` }))
    const panel = await screen.findByRole('article')
    expect(getAdminCase).toHaveBeenCalledWith(AMIT_P1, expect.anything())
    expect(within(panel).getByRole('heading', { name: /Amit Verma, / })).toBeVisible()
    expect(within(panel).getByText('engine template')).toBeVisible()
    expect(within(panel).getByText('left around 7:30ish')).toBeVisible()
    expect(within(panel).getByText('Makes the day 9.5 h.')).toBeVisible()
    expect(within(panel).getByText('Approving a 19:30 clock-out makes the day 9.5 h.')).toBeVisible()
    const timeline = within(panel).getByRole('region', { name: 'Audit trail' })
    const steps = within(timeline).getAllByRole('listitem')
    expect(steps.map((li) => li.textContent)).toEqual([
      'systemFound by the rule engine.',
      'Ravi KumarApproved: Set clock-out to 19:30.awaiting supervisor, with Ravi Kumar → resolved, with Ravi Kumar',
    ])
    expect(within(panel).getByText('get_schedule')).toBeVisible()
    expect(within(panel).queryByRole('button', { name: /Investigate/ })).toBeNull()
  })

  it('investigates an open case, polls the job and reloads', async () => {
    const user = userEvent.setup()
    vi.mocked(startInvestigation).mockResolvedValue('/api/exceptions/x/investigate/job1')
    vi.mocked(pollInvestigation)
      .mockResolvedValueOnce({ id: 'job1', status: 'running' } as never)
      .mockResolvedValueOnce({ id: 'job1', status: 'completed' } as never)
    render(<AdminPage />)
    await user.click(await screen.findByRole('button', { name: `Open ${AMIT_P1}` }))
    await user.click(await screen.findByRole('button', { name: 'Investigate' }))
    expect(screen.getByRole('button', { name: 'Investigating…' })).toBeDisabled()
    expect(await screen.findByText('Investigation stored.', {}, { timeout: 3000 })).toBeVisible()
    expect(startInvestigation).toHaveBeenCalledWith(AMIT_P1, expect.anything(), 'E201')
    expect(pollInvestigation).toHaveBeenCalledTimes(2)
    expect(pollInvestigation).toHaveBeenLastCalledWith('/api/exceptions/x/investigate/job1', expect.anything(), 'E201')
    // The reload runs in an effect after the notice renders; wait for it under load.
    await waitFor(() => expect(getAdminCase).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(getAdminOverview).toHaveBeenCalledTimes(2))
  })

  it('shows an investigate refusal in plain words', async () => {
    const user = userEvent.setup()
    vi.mocked(startInvestigation).mockRejectedValue(new ApiError(404, 'exception_not_found', 'gone'))
    render(<AdminPage />)
    await user.click(await screen.findByRole('button', { name: `Open ${AMIT_P1}` }))
    await user.click(await screen.findByRole('button', { name: 'Investigate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This case no longer exists.')
  })

  it('marks an escalated case and opens the decision card as Priya', async () => {
    const user = userEvent.setup()
    vi.mocked(getAdminCase).mockResolvedValue(makeCase({
      exception_id: MEENA_P5, status: 'escalated', assigned_to: 'E201', assigned_to_name: 'Priya Sharma',
      needs_your_decision: true, can_investigate: false,
      employee: { employee_id: 'E002', name: 'Meena Iyer', team: 'Inbound' },
    }))
    vi.mocked(getCase).mockReturnValue(new Promise(() => {}))
    render(<AdminPage />)
    await user.click(await screen.findByRole('button', { name: `Open ${MEENA_P5}` }))
    const note = await screen.findByRole('note')
    expect(note).toHaveTextContent('Needs your decision.')
    await user.click(within(note).getByRole('button', { name: 'Open the decision card' }))
    expect(getCase).toHaveBeenCalledWith(MEENA_P5, expect.anything(), 'E201')
    expect(await screen.findByText('Loading the case…')).toBeVisible()
  })
})
