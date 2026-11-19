// Phase 13: the no-reply badges and stage labels, deciding without the worker, escalate,
// and the demo clock control.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminPage } from './AdminPage'
import {
  ApiError,
  approveCase,
  escalateCase,
  getAdminOverview,
  getAutoResolveMetric,
  getCase,
  getQueue,
  getSchedulerStatus,
  getTeamAutoFixes,
  moveDemoClock,
  type AdminItem,
  type AdminOverview,
  type CaseOption,
  type NoReply,
  type QueueItem,
  type SupervisorCase,
} from './api'
import { cycleLine, SchedulerPanel } from './SchedulerPanel'
import { noReplyBadge, plainError, SupervisorPage } from './SupervisorPage'
import { cycle, metric, schedulerStatus } from './testFixtures'

vi.mock('./api', async (importOriginal) => ({
  ...await importOriginal<typeof import('./api')>(),
  getQueue: vi.fn(),
  getCase: vi.fn(),
  approveCase: vi.fn(),
  escalateCase: vi.fn(),
  getTeamAutoFixes: vi.fn(),
  getSchedulerStatus: vi.fn(),
  moveDemoClock: vi.fn(),
  runSchedulerNow: vi.fn(),
  getAdminOverview: vi.fn(),
  getAutoResolveMetric: vi.fn(),
}))

const NEHA_P1 = 'P1-E004-2026-04-15'
const REASON = 'Neha is on leave; the gate log shows 18:00.'

const stage2: NoReply = {
  stage: 2,
  stage_key: 'supervisor',
  label: 'Supervisor brought in',
  note: 'Neha Gupta has not replied for 26 h.',
  hours_without_reply: '26 h',
  wait_since: '2026-04-16T08:00:00',
  reminded_at: '2026-04-16T16:00:00',
  supervisor_at: '2026-04-17T08:00:00',
  admin_at: null,
  late_reply_at: null,
  can_decide_without_worker: true,
}

const queueItem: QueueItem = {
  exception_id: NEHA_P1,
  employee_id: 'E004',
  employee_name: 'Neha Gupta',
  date: '2026-04-15',
  policy_id: 'P1',
  title: 'Every shift needs a clock-in and a clock-out',
  summary: 'Clock-in 08:58, no clock-out (scheduled end 18:00)',
  severity: 'high',
  kind: 'breach',
  status: 'awaiting_supervisor',
  waiting_since: '2026-04-17T08:00:00',
  auto_resolve_undone: false,
  no_reply: stage2,
}

const clockOut: CaseOption = {
  option_id: 'set_clock_out_to_scheduled_end',
  action: 'set_clock_out',
  label: 'Set clock-out to 18:00',
  description: 'Adds a correction clock-out punch at the given time.',
  params: { timestamp: '2026-04-15T18:00:00' },
  decision_only: false,
  requires_worker_confirmation: true,
  worker_confirmed: false,
  note_field: null,
  fields: [{ name: 'timestamp', kind: 'datetime', value: '2026-04-15T18:00:00', editable: true, locked_reason: null }],
  punches: null,
  consequence: {
    source: 'investigation',
    note: 'Approving a 18:00 clock-out makes the day 8 h and projects 40 h for the week. It creates no new exceptions.',
    creates_violations: false,
    new_violations: [],
    resolved: [],
    day_worked_hours: 8,
    week_projected_hours: 40,
    weekly_limit_hours: 40,
  },
}

function card(overrides: Partial<SupervisorCase> = {}): SupervisorCase {
  return {
    exception_id: NEHA_P1,
    status: 'awaiting_supervisor',
    assigned_to: 'E101',
    employee: { employee_id: 'E004', name: 'Neha Gupta', team: 'Inbound' },
    date: '2026-04-15',
    policy_id: 'P1',
    title: queueItem.title,
    summary: queueItem.summary,
    severity: 'high',
    kind: 'breach',
    details: {},
    policy: { policy_id: 'P1', title: 'Missing punch', rule: 'r', cited_text: 'Every worked shift must have a clock-out.' },
    evidence: [],
    other_workers_evidence_hidden: 0,
    investigation: null,
    worker: { replied: false, confirmed: null, reply_text: null, replied_at: null, needs_actual_time: false },
    confirmed_time: null,
    recheck: null,
    options: [clockOut],
    applied_fix: null,
    min_note_length: 3,
    can_decide: true,
    trace: [],
    no_reply: stage2,
    ...overrides,
  }
}

async function openNeha(data = card()) {
  vi.mocked(getQueue).mockResolvedValue([queueItem])
  vi.mocked(getCase).mockResolvedValue(data)
  vi.mocked(getTeamAutoFixes).mockResolvedValue([])
  const user = userEvent.setup()
  render(<SupervisorPage />)
  await user.click(await screen.findByRole('button', { name: /Neha Gupta/ }))
  await screen.findByRole('heading', { name: /Neha Gupta, / })
  return user
}

describe('no-reply badges', () => {
  it('says how long the worker has been silent, or that they replied late', () => {
    expect(noReplyBadge(stage2)).toBe('no reply · 26 h')
    expect(noReplyBadge({ ...stage2, stage: 0, hours_without_reply: null, label: 'Replied late' })).toBe('replied late')
    expect(noReplyBadge(null)).toBe('')
  })

  it('counts the ladder steps in the cycle line', () => {
    const line = cycleLine(cycle({ no_reply: { enabled: true, reminded: ['A'], to_supervisor: ['B', 'C'], to_admin: ['D'] } }))
    expect(line).toContain('1 reminder sent')
    expect(line).toContain('2 sent to the supervisor (no reply)')
    expect(line).toContain('1 sent to payroll (no reply)')
  })

  it('explains the new refusals in plain words', () => {
    expect(plainError(new ApiError(422, 'time_confirmation_required', 'x'), 'Neha Gupta'))
      .toBe('Tick "I\'m confirming this time without the worker\'s reply" first.')
    expect(plainError(new ApiError(409, 'no_reply_not_escalated', 'x'), 'Neha Gupta'))
      .toBe('You can decide without Neha only after they missed the reply deadline.')
  })
})

describe('supervisor: no reply', () => {
  beforeEach(() => vi.resetAllMocks())

  it('shows the badge in the queue and the note on the card', async () => {
    await openNeha()
    const row = screen.getByRole('button', { name: /Neha Gupta/ })
    expect(within(row).getByText('no reply · 26 h')).toBeVisible()
    const note = screen.getByRole('region', { name: 'No reply' })
    expect(note).toHaveTextContent('Supervisor brought in')
    expect(note).toHaveTextContent('Neha Gupta has not replied for 26 h.')
  })

  it('decides without the worker only with a reason and the explicit time tick', async () => {
    vi.mocked(approveCase).mockResolvedValue({
      status: 'resolved',
      applied_fix: { label: 'Set clock-out to 18:00' },
      detection: { ran: true, new_exception_ids: [], closed_exception_ids: [], error: null },
    } as never)
    const user = await openNeha()
    expect(screen.getByText("Needs Neha's confirmation first.")).toBeVisible()
    await user.click(screen.getByRole('checkbox', { name: "Decide on the evidence without Neha's reply" }))
    expect(screen.queryByText("Needs Neha's confirmation first.")).not.toBeInTheDocument()
    const approve = screen.getByRole('button', { name: 'Approve without reply' })
    expect(approve).toBeDisabled()
    await user.type(screen.getByLabelText(/Reason \(required/), REASON)
    expect(approve).toBeDisabled() // the time still needs the tick
    await user.click(screen.getByRole('checkbox', { name: "I'm confirming this time without the worker's reply" }))
    expect(approve).toBeEnabled()
    await user.click(approve)
    expect(approveCase).toHaveBeenCalledWith(NEHA_P1, {
      option_id: clockOut.option_id,
      reason: REASON,
      without_worker: true,
      confirm_time_without_worker: true,
    }, 'E101')
  })

  it('sends the case to payroll with a reason', async () => {
    vi.mocked(escalateCase).mockResolvedValue({ status: 'escalated', assigned_to: 'E201' } as never)
    const user = await openNeha()
    await user.click(screen.getByRole('button', { name: 'Send to payroll' }))
    await user.type(screen.getByLabelText(/Why should payroll decide/), 'Cannot verify the time')
    await user.click(screen.getByRole('button', { name: 'Send to payroll' }))
    expect(escalateCase).toHaveBeenCalledWith(NEHA_P1, { reason: 'Cannot verify the time' }, 'E101')
    expect(await screen.findByText(/Sent to the payroll admin \(E201\)/)).toBeVisible()
  })

  it('offers neither choice on a case the ladder has not brought in', async () => {
    await openNeha(card({ no_reply: null }))
    expect(screen.queryByRole('checkbox', { name: /without Neha/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send to payroll' })).not.toBeInTheDocument()
  })
})

describe('demo clock control', () => {
  beforeEach(() => vi.resetAllMocks())

  it('shows the time and moves the clock forward in demo mode, with the hint', async () => {
    const movable = schedulerStatus({
      demo_mode: true,
      clock: {
        now: '2026-04-16T08:00:00', data_as_of: '2026-04-16T08:00:00',
        offset_hours: 0, max_offset_hours: 336, movable: true, hint: null,
      },
    })
    vi.mocked(getSchedulerStatus).mockResolvedValue(movable)
    vi.mocked(moveDemoClock).mockResolvedValue({
      now: '2026-04-16T16:00:00', data_as_of: '2026-04-16T08:00:00', offset_hours: 8,
      max_offset_hours: 336, movable: true,
      hint: 'Run the scheduler (or wait for the next cycle) to apply.',
    })
    const user = userEvent.setup()
    render(<SchedulerPanel onChanged={vi.fn()} pollMs={60_000} />)
    expect(await screen.findByTestId('demo-now')).toHaveTextContent('Thu 16 Apr 08:00')
    await user.click(screen.getByRole('button', { name: 'Move the demo clock +8 h' }))
    expect(moveDemoClock).toHaveBeenCalledWith(8)
    expect(await screen.findByText(
      'Demo clock is now Thu 16 Apr 16:00. Run the scheduler (or wait for the next cycle) to apply.',
    )).toBeVisible()
  })

  it('shows the fixed clock and no controls outside demo mode', async () => {
    vi.mocked(getSchedulerStatus).mockResolvedValue(schedulerStatus())
    render(<SchedulerPanel onChanged={vi.fn()} />)
    expect(await screen.findByTestId('demo-now')).toHaveTextContent('Thu 16 Apr 08:00')
    expect(screen.queryByRole('group', { name: 'Move the demo clock' })).not.toBeInTheDocument()
  })

  it('explains the 14-day limit', async () => {
    vi.mocked(getSchedulerStatus).mockResolvedValue(schedulerStatus({
      demo_mode: true,
      clock: { now: '2026-04-30T00:00:00', data_as_of: '2026-04-16T08:00:00', offset_hours: 328, max_offset_hours: 336, movable: true, hint: null },
    }))
    vi.mocked(moveDemoClock).mockRejectedValue(new ApiError(422, 'clock_limit', 'x'))
    const user = userEvent.setup()
    render(<SchedulerPanel onChanged={vi.fn()} pollMs={60_000} />)
    await user.click(await screen.findByRole('button', { name: 'Move the demo clock +1 day' }))
    expect(await screen.findByText(/cannot move more than 14 days/)).toBeVisible()
  })
})

describe('admin: stuck cases', () => {
  beforeEach(() => vi.resetAllMocks())

  function adminItem(overrides: Partial<AdminItem> = {}): AdminItem {
    return {
      exception_id: NEHA_P1, employee_id: 'E004', employee_name: 'Neha Gupta', team: 'Inbound',
      date: '2026-04-15', policy_id: 'P1', title: queueItem.title, summary: queueItem.summary,
      severity: 'high', kind: 'breach', status: 'awaiting_supervisor', auto_resolved: false,
      auto_resolve_undone: false, assigned_to: 'E101', assigned_to_name: 'Ravi Kumar',
      investigated: true, who_to_ask: 'worker', investigation_fallback: true,
      needs_your_decision: false, updated_at: '2026-04-17T08:00:00', no_reply: stage2,
      ...overrides,
    }
  }

  function overviewWith(items: AdminItem[]): AdminOverview {
    return {
      counters: {
        total: 18, open: 15, awaiting_worker: 0, awaiting_supervisor: 1, escalated: 0,
        resolved: 2, rejected: 0, auto_resolved: 1, stuck: 1,
      },
      matched: items.length, limit: 200, offset: 0, items,
      filter_options: {
        statuses: [], policy_ids: [], teams: [], employees: [], severities: [],
        no_reply: ['any', 'reminded', 'supervisor', 'payroll_admin'],
      },
    }
  }

  it('shows the stuck counter, the stage label, and filters by it', async () => {
    vi.mocked(getAdminOverview).mockResolvedValue(overviewWith([adminItem()]))
    vi.mocked(getSchedulerStatus).mockResolvedValue(schedulerStatus())
    vi.mocked(getAutoResolveMetric).mockResolvedValue(metric())
    const user = userEvent.setup()
    render(<AdminPage />)
    const tile = await screen.findByRole('button', { name: 'Stuck (no reply): 1' })
    expect(screen.getByText('Supervisor brought in · no reply · 26 h')).toBeVisible()
    await user.click(tile)
    await waitFor(() => expect(getAdminOverview).toHaveBeenLastCalledWith(
      expect.objectContaining({ no_reply: 'any' }), expect.anything(),
    ))
    await user.selectOptions(screen.getByLabelText('No reply'), 'payroll_admin')
    await waitFor(() => expect(getAdminOverview).toHaveBeenLastCalledWith(
      expect.objectContaining({ no_reply: 'payroll_admin' }), expect.anything(),
    ))
  })
})
