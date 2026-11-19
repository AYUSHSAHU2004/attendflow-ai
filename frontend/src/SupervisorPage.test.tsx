import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  approveCase,
  editCase,
  getCase,
  getQueue,
  getTeamAutoFixes,
  rejectCase,
  type ApproveResult,
  type CaseOption,
  type QueueItem,
  type SupervisorCase,
} from './api'
import { plainError, SupervisorPage } from './SupervisorPage'

vi.mock('./api', async (importOriginal) => ({
  ...await importOriginal<typeof import('./api')>(),
  getQueue: vi.fn(),
  getCase: vi.fn(),
  approveCase: vi.fn(),
  editCase: vi.fn(),
  rejectCase: vi.fn(),
  getTeamAutoFixes: vi.fn(),
}))

const AMIT_P1 = 'P1-E001-2026-04-14'
const item: QueueItem = {
  exception_id: AMIT_P1,
  employee_id: 'E001',
  employee_name: 'Amit Verma',
  date: '2026-04-14',
  policy_id: 'P1',
  title: 'Every shift needs a clock-in and a clock-out',
  summary: 'Clock-in 09:00, no clock-out (scheduled end 18:00)',
  severity: 'high',
  kind: 'breach',
  status: 'awaiting_supervisor',
  waiting_since: '2026-04-16T08:00:00',
  auto_resolve_undone: false,
}

const newViolations = [
  { policy_id: 'P3', kind: 'breach' as const, date: '2026-04-14', reason: 'Worked 9.5 h' },
  { policy_id: 'P5', kind: 'risk' as const, date: '2026-04-13', reason: '41.5 h projected' },
]

const clockOut: CaseOption = {
  option_id: 'set_clock_out_to_scheduled_end',
  action: 'set_clock_out',
  label: 'Set clock-out to 19:30 (worker-confirmed, approximate)',
  description: 'Adds a correction clock-out punch at the given time.',
  params: { timestamp: '2026-04-14T19:30:00' },
  decision_only: false,
  requires_worker_confirmation: true,
  worker_confirmed: true,
  note_field: null,
  fields: [{
    name: 'timestamp', kind: 'datetime', value: '2026-04-14T19:30:00', editable: false,
    locked_reason: 'To change it, Amit Verma must confirm a new time.',
  }],
  punches: null,
  consequence: {
    source: 'worker_recheck',
    note: 'Approving a 19:30 clock-out makes the day 9.5 h, over the 9 h limit (P3) and projects 41.5 h for the week, over 40 h (P5). Approving creates 2 new exceptions: P3, P5.',
    creates_violations: true,
    new_violations: newViolations,
    resolved: [],
    day_worked_hours: 9.5,
    week_projected_hours: 41.5,
    weekly_limit_hours: 40,
  },
}

function makeCase(overrides: Partial<SupervisorCase> = {}): SupervisorCase {
  return {
    exception_id: AMIT_P1,
    status: 'awaiting_supervisor',
    assigned_to: 'E101',
    employee: { employee_id: 'E001', name: 'Amit Verma', team: 'Inbound' },
    date: '2026-04-14',
    policy_id: 'P1',
    title: item.title,
    summary: item.summary,
    severity: 'high',
    kind: 'breach',
    details: {},
    policy: {
      policy_id: 'P1',
      title: 'Missing punch',
      rule: 'Every worked shift must have one clock-in and one clock-out.',
      cited_text: 'Every worked shift must have exactly one clock-in and one clock-out punch.',
    },
    evidence: [],
    other_workers_evidence_hidden: 0,
    investigation: null,
    worker: {
      replied: true, confirmed: false, reply_text: 'stayed late to unload the truck, left around 7:30ish',
      replied_at: '2026-04-16T08:00:00', needs_actual_time: false,
    },
    confirmed_time: {
      timestamp: '2026-04-14T19:30:00', approximate: true, source: 'llm', option_id: clockOut.option_id,
    },
    recheck: {
      ok: true, employee_id: 'E001', week: '2026-04-13 to 2026-04-19', verdict: '2 new violations',
      new_violations: newViolations, resolved: [], still_open: [],
      day_worked_hours: 9.5, week_projected_hours: 41.5, weekly_limit_hours: 40,
    },
    options: [clockOut],
    applied_fix: null,
    min_note_length: 3,
    ...overrides,
  }
}

const approved = {
  status: 'resolved',
  applied_fix: { label: clockOut.label },
  detection: { ran: true, new_exception_ids: ['P3-E001-2026-04-14', 'P5-E001-2026-04-13'], closed_exception_ids: [], error: null },
} as unknown as ApproveResult

async function openCase(caseData: SupervisorCase) {
  vi.mocked(getQueue).mockResolvedValue([item])
  vi.mocked(getCase).mockResolvedValue(caseData)
  const user = userEvent.setup()
  render(<SupervisorPage />)
  await user.click(await screen.findByRole('button', { name: /Amit Verma/ }))
  await screen.findByRole('heading', { name: /Amit Verma, / })
  return user
}

describe('supervisor queue', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(getTeamAutoFixes).mockResolvedValue([])
  })

  it('shows the empty state', async () => {
    vi.mocked(getQueue).mockResolvedValue([])
    render(<SupervisorPage />)
    expect(await screen.findByText('Nothing needs your decision')).toBeVisible()
  })

  it('shows a plain error and retries', async () => {
    vi.mocked(getQueue)
      .mockRejectedValueOnce(new ApiError(403, 'supervisor_only', 'only a supervisor ...'))
      .mockResolvedValueOnce([])
    const user = userEvent.setup()
    render(<SupervisorPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Only a supervisor or the payroll admin can do this.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Nothing needs your decision')).toBeVisible()
  })

  it('lists cases with employee, date, policy, severity and summary', async () => {
    vi.mocked(getQueue).mockResolvedValue([item])
    render(<SupervisorPage />)
    const row = await screen.findByRole('button', { name: /Amit Verma/ })
    expect(row).toHaveTextContent('P1')
    expect(row).toHaveTextContent('high')
    expect(row).toHaveTextContent('14 April 2026')
    expect(row).toHaveTextContent(item.summary)
  })
})

describe('case card', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(getTeamAutoFixes).mockResolvedValue([])
  })

  it('shows the approximate time, the worker\'s words, the re-check and the consequence', async () => {
    await openCase(makeCase())
    const said = screen.getByRole('region', { name: 'What the worker said' })
    expect(said).toHaveTextContent('19:30')
    expect(within(said).getByText('approximate')).toBeVisible()
    expect(said).toHaveTextContent('left around 7:30ish')
    expect(screen.getByRole('region', { name: 'Re-check' })).toHaveTextContent('Day worked: 9.5 h')
    expect(screen.getByRole('radio', { name: /Set clock-out to 19:30/ })).toBeChecked()
    expect(screen.getByText(clockOut.consequence.note)).toBeVisible()
    expect(screen.getByRole('region', { name: 'Policy' })).toHaveTextContent('exactly one clock-in')
  })

  it('asks for confirmation before approving a fix that creates violations', async () => {
    vi.mocked(approveCase).mockResolvedValue(approved)
    const user = await openCase(makeCase())
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    const confirm = screen.getByRole('alertdialog', { name: 'Confirm approval' })
    expect(confirm).toHaveTextContent('Approving creates new exceptions')
    expect(approveCase).not.toHaveBeenCalled()
    vi.mocked(getCase).mockResolvedValue(makeCase({ status: 'resolved', applied_fix: { label: clockOut.label, approved_by: 'E101' } }))
    await user.click(within(confirm).getByRole('button', { name: 'Approve anyway' }))
    expect(approveCase).toHaveBeenCalledWith(AMIT_P1, { option_id: clockOut.option_id, reason: undefined }, 'E101')
    expect(await screen.findByRole('status')).toHaveTextContent('New exceptions opened: P3-E001-2026-04-14, P5-E001-2026-04-13.')
    expect(getQueue).toHaveBeenCalledTimes(2)
    expect(await screen.findByRole('region', { name: 'Decision' })).toHaveTextContent('by E101')
  })

  it('locks a worker-confirmed P1 time, so there is nothing to edit', async () => {
    await openCase(makeCase())
    expect(screen.getByRole('button', { name: 'Edit' })).toBeDisabled()
  })

  it('requires the note for a decision-only option', async () => {
    const accept: CaseOption = {
      ...clockOut, option_id: 'accept_reason', action: 'accept_reason', label: 'Accept the reason',
      decision_only: true, requires_worker_confirmation: false, worker_confirmed: false,
      note_field: 'reason', fields: [],
      consequence: { ...clockOut.consequence, source: 'decision_only', note: 'Records a decision only.', creates_violations: false, new_violations: [] },
    }
    vi.mocked(approveCase).mockResolvedValue({ ...approved, detection: { ...approved.detection, ran: false, new_exception_ids: [] } })
    const user = await openCase(makeCase({ options: [accept], confirmed_time: null, recheck: null }))
    const approve = screen.getByRole('button', { name: 'Approve' })
    expect(approve).toBeDisabled()
    await user.type(screen.getByLabelText(/reason \(required/), 'ok')
    expect(approve).toBeDisabled()
    await user.type(screen.getByLabelText(/reason \(required/), ' - bus strike')
    await user.click(approve)
    expect(approveCase).toHaveBeenCalledWith(AMIT_P1, { option_id: 'accept_reason', reason: 'ok - bus strike' }, 'E101')
  })

  it('edits P13 punch times with validation', async () => {
    const editPunches: CaseOption = {
      ...clockOut, option_id: 'edit_punches', action: 'edit_punches',
      label: 'Keep the leave and correct the punches', params: { punch_ids: ['P0060', 'P0065'] },
      fields: [{ name: 'punch_ids', kind: 'fixed', value: ['P0060', 'P0065'], editable: false, locked_reason: null }],
      punches: [
        { punch_id: 'P0060', type: 'in', timestamp: '2026-04-15T09:00:00' },
        { punch_id: 'P0065', type: 'out', timestamp: '2026-04-15T18:00:00' },
      ],
      consequence: { ...clockOut.consequence, source: 'unchecked', note: 'Not checked yet.', creates_violations: false, new_violations: [] },
    }
    vi.mocked(editCase)
      .mockRejectedValueOnce(new ApiError(422, 'invalid_params', 'invalid params for edit_punches', [
        { loc: 'changes.0.timestamp', msg: 'Input should be a valid datetime' },
      ]))
      .mockResolvedValueOnce({ ...approved, detection: { ...approved.detection, new_exception_ids: [] } })
    const user = await openCase(makeCase({ options: [editPunches], confirmed_time: null, recheck: null }))
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    const form = screen.getByRole('form', { name: 'Edit the fix' })
    await user.click(within(form).getByRole('button', { name: 'Save and approve' }))
    expect(within(form).getByRole('alert')).toHaveTextContent('Change at least one value')

    const out = within(form).getByLabelText('out (P0065)')
    await user.clear(out)
    await user.type(out, '2026-04-15T13:00')
    await user.click(within(form).getByRole('button', { name: 'Save and approve' }))
    expect(within(form).getByRole('alert')).toHaveTextContent('Give a reason')
    expect(editCase).not.toHaveBeenCalled()

    await user.type(within(form).getByLabelText('Reason for the change'), 'Farah left at 13:00')
    await user.click(within(form).getByRole('button', { name: 'Save and approve' }))
    expect(editCase).toHaveBeenCalledWith(AMIT_P1, {
      option_id: 'edit_punches',
      params: { changes: [{ punch_id: 'P0065', timestamp: '2026-04-15T13:00' }] },
      reason: 'Farah left at 13:00',
    }, 'E101')
    expect(await screen.findByText(/Some values are not valid: Input should be a valid datetime/)).toBeVisible()

    await user.click(within(form).getByRole('button', { name: 'Save and approve' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Approved for Amit Verma')
  })

  it('requires a reject reason and reports the escalation', async () => {
    vi.mocked(rejectCase).mockResolvedValue({ ...makeCase(), status: 'escalated', assigned_to: 'E201' } as never)
    const user = await openCase(makeCase())
    await user.click(screen.getByRole('button', { name: 'Reject' }))
    await user.type(screen.getByLabelText(/Why are you rejecting/), 'too short')
    await user.click(screen.getByRole('button', { name: 'Send reject' }))
    expect(screen.getByRole('alert')).toHaveTextContent('at least 10 characters')
    expect(rejectCase).not.toHaveBeenCalled()
    await user.type(screen.getByLabelText(/Why are you rejecting/), ', camera shows 18:05')
    await user.click(screen.getByRole('button', { name: 'Send reject' }))
    expect(rejectCase).toHaveBeenCalledWith(AMIT_P1, { reason: 'too short, camera shows 18:05' }, 'E101')
    expect(await screen.findByRole('status')).toHaveTextContent('sent to the payroll admin (E201)')
    expect(screen.queryByRole('heading', { name: /Amit Verma, / })).not.toBeInTheDocument()
  })

  it('explains a 409 from the server in plain words', async () => {
    vi.mocked(approveCase).mockRejectedValue(
      new ApiError(409, 'worker_not_confirmed', 'the worker must confirm the punch time first'),
    )
    const user = await openCase(makeCase())
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    await user.click(screen.getByRole('button', { name: 'Approve anyway' }))
    expect(await screen.findByText('Amit has not confirmed this time yet. Wait for their reply before approving.')).toBeVisible()
  })
})

describe('plain error messages', () => {
  it('covers each refusal', () => {
    expect(plainError(new ApiError(409, 'worker_not_confirmed', 'x'), 'Karan Mehta')).toBe(
      'Karan has not confirmed this yet. Ask them first, then approve after they reply Yes.',
    )
    expect(plainError(new ApiError(409, 'invalid_transition', 'x'))).toMatch(/already moved on/)
    expect(plainError(new ApiError(403, 'not_assigned', 'x'))).toBe('This case is not assigned to you, so you cannot act on it.')
    expect(plainError(new ApiError(422, 'validation_error', 'x', [{ loc: 'body.reason', msg: 'too short' }]))).toBe(
      'Some values are not valid: too short',
    )
    expect(plainError(new TypeError('Failed to fetch'))).toMatch(/could not be reached/)
  })
})
