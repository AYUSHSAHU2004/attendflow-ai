import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminPage } from './AdminPage'
import {
  ApiError,
  getAdminOverview,
  getSchedulerStatus,
  runSchedulerNow,
  sendDemoPunch,
  type AdminOverview,
  type PunchAccepted,
} from './api'
import { POLL_MS, SchedulerPanel } from './SchedulerPanel'
import { cycle, schedulerStatus } from './testFixtures'

// The briefing card has its own tests (BriefingCard.test.tsx).
vi.mock('./BriefingCard', () => ({ BriefingCard: () => null }))
vi.mock('./api', async (importOriginal) => ({
  ...await importOriginal<typeof import('./api')>(),
  getSchedulerStatus: vi.fn(),
  runSchedulerNow: vi.fn(),
  sendDemoPunch: vi.fn(),
  getAdminOverview: vi.fn(),
}))

const workers = [
  { employee_id: 'E001', name: 'Amit Verma', team: 'Inbound' },
  { employee_id: 'E004', name: 'Neha Gupta', team: 'Inbound' },
]
const demoStatus = () => schedulerStatus({ demo_mode: true, workers })

const accepted: PunchAccepted = {
  punch: {
    punch_id: 'P0073', employee_id: 'E004', timestamp: '2026-04-15T08:58:00', type: 'in',
    source: 'device', device_id: 'GATE-01', location: 'Warehouse 1 - Inbound Gate',
  },
  detection: {
    ran: true,
    scope: { employee_id: 'E004', start: '2026-04-13', end: '2026-04-19' },
    new_exception_ids: ['P1-E004-2026-04-15'],
    closed_exception_ids: ['P10-E004-2026-04-15'],
    updated: 0,
    error: null,
  },
}

const emptyOverview: AdminOverview = {
  counters: {
    total: 0, open: 0, awaiting_worker: 0, awaiting_supervisor: 0, escalated: 0,
    resolved: 0, rejected: 0, auto_resolved: 0, stuck: 0,
  },
  matched: 0, limit: 200, offset: 0, items: [],
  filter_options: { statuses: [], policy_ids: [], teams: [], employees: [], severities: [] },
}

async function fillPunch(user: ReturnType<typeof userEvent.setup>) {
  const form = await screen.findByRole('form', { name: 'Simulate punch' })
  await user.selectOptions(within(form).getByLabelText('Worker'), 'E004')
  await user.selectOptions(within(form).getByLabelText('Punch'), 'in')
  const date = within(form).getByLabelText('Date')
  await user.clear(date)
  await user.type(date, '2026-04-15')
  const time = within(form).getByLabelText('Time')
  await user.clear(time)
  await user.type(time, '08:58')
  return form
}

beforeEach(() => {
  vi.mocked(getSchedulerStatus).mockReset().mockResolvedValue(demoStatus())
  vi.mocked(runSchedulerNow).mockReset()
  vi.mocked(sendDemoPunch).mockReset()
  vi.mocked(getAdminOverview).mockReset().mockResolvedValue(emptyOverview)
})

describe('SchedulerPanel', () => {
  it('hides the punch simulator when demo mode is off, but keeps the status and Run now', async () => {
    vi.mocked(getSchedulerStatus).mockResolvedValue(schedulerStatus())
    render(<SchedulerPanel onChanged={vi.fn()} />)
    expect(await screen.findByTestId('scheduler-status')).toHaveTextContent('Scheduler off · no cycle yet')
    expect(screen.getByRole('button', { name: 'Run scheduler now' })).toBeEnabled()
    expect(screen.queryByRole('form', { name: 'Simulate punch' })).toBeNull()
    expect(screen.queryByRole('button', { name: /simulat/i })).toBeNull()
  })

  it('the admin page has no simulator when demo mode is off', async () => {
    vi.mocked(getSchedulerStatus).mockResolvedValue(schedulerStatus())
    render(<AdminPage />)
    expect(await screen.findByTestId('scheduler-status')).toBeVisible()
    expect(screen.queryByRole('form', { name: 'Simulate punch' })).toBeNull()
  })

  it('shows the last cycle in the status line', async () => {
    vi.mocked(getSchedulerStatus).mockResolvedValue(schedulerStatus({
      running: true,
      interval_seconds: 15,
      last_cycle: cycle({
        new: 1,
        investigated: [{
          exception_id: 'P1-E004-2026-04-15', job_id: 'j1', job_status: 'completed',
          reason: 'validated', fallback: false, who_to_ask: 'worker', duration_ms: 3100,
        }],
        messages_sent: ['P1-E004-2026-04-15'],
        skipped_backlog: 15,
      }),
    }))
    render(<SchedulerPanel onChanged={vi.fn()} />)
    const line = await screen.findByTestId('scheduler-status')
    expect(line).toHaveTextContent('Scheduler on (every 15 s)')
    expect(line).toHaveTextContent('1 new, 1 investigated, 1 message sent, 15 older cases left alone')
  })

  it('sends a simulated punch and refreshes the list', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn()
    vi.mocked(sendDemoPunch).mockResolvedValue(accepted)
    render(<SchedulerPanel onChanged={onChanged} />)
    const form = await fillPunch(user)
    await user.click(within(form).getByRole('button', { name: 'Send' }))
    expect(sendDemoPunch).toHaveBeenCalledWith({
      employee_id: 'E004', type: 'in', timestamp: '2026-04-15T08:58', source: 'device',
    })
    expect(await screen.findByText(
      'Punch P0073 stored. New: P1-E004-2026-04-15. Closed: P10-E004-2026-04-15.',
    )).toBeVisible()
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  it('defaults the form to the demo clock', async () => {
    render(<SchedulerPanel onChanged={vi.fn()} />)
    const form = await screen.findByRole('form', { name: 'Simulate punch' })
    expect(within(form).getByLabelText('Date')).toHaveValue('2026-04-16')
    expect(within(form).getByLabelText('Time')).toHaveValue('08:00')
    expect(form).toHaveTextContent('Punches after 2026-04-16 08:00 (the data cut-off) are refused.')
  })

  it('explains a refused punch and does not refresh', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn()
    vi.mocked(sendDemoPunch).mockRejectedValue(
      new ApiError(422, 'punch_in_future', 'thu 16 Apr 08:30 is after now (Thu 16 Apr 08:00)'),
    )
    render(<SchedulerPanel onChanged={onChanged} />)
    const form = await fillPunch(user)
    await user.click(within(form).getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Thu 16 Apr 08:30 is after now (Thu 16 Apr 08:00).')).toBeVisible()
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('shows a request validation error in plain words', async () => {
    const user = userEvent.setup()
    vi.mocked(sendDemoPunch).mockRejectedValue(new ApiError(422, 'validation_error', 'the request is not valid', [
      { loc: 'body.timestamp', msg: 'String should match pattern', type: 'string_pattern_mismatch' },
    ]))
    render(<SchedulerPanel onChanged={vi.fn()} />)
    const form = await fillPunch(user)
    await user.click(within(form).getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(/Some values are not valid/)).toBeVisible()
  })

  it('asks for a date and time before sending', async () => {
    const user = userEvent.setup()
    render(<SchedulerPanel onChanged={vi.fn()} />)
    const form = await screen.findByRole('form', { name: 'Simulate punch' })
    await user.clear(within(form).getByLabelText('Time'))
    await user.click(within(form).getByRole('button', { name: 'Send' }))
    expect(screen.getByText('Pick a worker, a date and a time.')).toBeVisible()
    expect(sendDemoPunch).not.toHaveBeenCalled()
  })

  it('explains a 403 on send', async () => {
    const user = userEvent.setup()
    vi.mocked(sendDemoPunch).mockRejectedValue(new ApiError(403, 'admin_only', 'only the payroll admin'))
    render(<SchedulerPanel onChanged={vi.fn()} />)
    const form = await fillPunch(user)
    await user.click(within(form).getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(
      'Only the payroll admin can use the scheduler and the punch simulator.',
    )).toBeVisible()
  })

  it('stays out of the way when the status itself is a 403', async () => {
    vi.mocked(getSchedulerStatus).mockRejectedValue(new ApiError(403, 'admin_only', 'only the payroll admin'))
    const { container } = render(<SchedulerPanel onChanged={vi.fn()} />)
    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalled())
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })

  it('shows other status errors with a retry', async () => {
    const user = userEvent.setup()
    vi.mocked(getSchedulerStatus)
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(demoStatus())
    render(<SchedulerPanel onChanged={vi.fn()} />)
    expect(await screen.findByText(/Scheduler status unavailable: The server could not be reached/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('form', { name: 'Simulate punch' })).toBeVisible()
  })

  it('runs a cycle now and reports it', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn()
    vi.mocked(runSchedulerNow).mockResolvedValue(cycle({
      cycle_id: 2, new: 1, messages_sent: ['P1-E004-2026-04-15'],
      investigated: [{
        exception_id: 'P1-E004-2026-04-15', job_id: 'j1', job_status: 'completed',
        reason: 'validated', fallback: false, who_to_ask: 'worker', duration_ms: 3100,
      }],
    }))
    render(<SchedulerPanel onChanged={onChanged} />)
    await user.click(await screen.findByRole('button', { name: 'Run scheduler now' }))
    expect(await screen.findByText(
      'Cycle 2 done: 1 new, 1 investigated, 1 message sent, 16 older cases left alone.',
    )).toBeVisible()
    expect(onChanged).toHaveBeenCalled()
    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalledTimes(2))
  })

  it('explains a busy scheduler', async () => {
    const user = userEvent.setup()
    vi.mocked(runSchedulerNow).mockRejectedValue(new ApiError(409, 'scheduler_busy', 'busy'))
    render(<SchedulerPanel onChanged={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: 'Run scheduler now' }))
    expect(await screen.findByText('A scheduler cycle is already running. Try again in a moment.')).toBeVisible()
  })

  it('refreshes on its own while the simulator is open, and stops when hidden', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn()
    render(<SchedulerPanel onChanged={onChanged} pollMs={40} />)
    await screen.findByRole('form', { name: 'Simulate punch' })
    await waitFor(() => expect(onChanged.mock.calls.length).toBeGreaterThanOrEqual(2))
    expect(vi.mocked(getSchedulerStatus).mock.calls.length).toBeGreaterThanOrEqual(2)

    await user.click(screen.getByRole('button', { name: 'Hide punch simulator' }))
    const stopped = onChanged.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 200))
    expect(onChanged).toHaveBeenCalledTimes(stopped)
  })

  it('does not poll when demo mode is off', async () => {
    vi.mocked(getSchedulerStatus).mockResolvedValue(schedulerStatus())
    const onChanged = vi.fn()
    render(<SchedulerPanel onChanged={onChanged} pollMs={40} />)
    await screen.findByTestId('scheduler-status')
    await new Promise((resolve) => setTimeout(resolve, 200))
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('polls every few seconds by default', () => {
    expect(POLL_MS).toBeGreaterThanOrEqual(2000)
    expect(POLL_MS).toBeLessThanOrEqual(10000)
  })

  it('on the admin page, a punch refreshes the exceptions table', async () => {
    const user = userEvent.setup()
    vi.mocked(sendDemoPunch).mockResolvedValue(accepted)
    render(<AdminPage />)
    await screen.findByText('No exceptions match these filters.')
    const before = vi.mocked(getAdminOverview).mock.calls.length
    const form = await fillPunch(user)
    await user.click(within(form).getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(vi.mocked(getAdminOverview).mock.calls.length).toBeGreaterThan(before))
  })
})
