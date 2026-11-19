import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import type { PayrollReadiness, ReadinessReason } from './api'
import { PayrollPage } from './PayrollPage'

const closed: PayrollReadiness = {
  week_start: '2026-04-06',
  week_end: '2026-04-12',
  evaluated_through: '2026-04-12',
  data_cutoff: '2026-04-16T08:00:00',
  closed: true,
  has_data: true,
  status: 'ready',
  scope: 'all',
  can_sign: true,
  can_reopen: false,
  signoff: null,
  exception_counts: {
    total: 0, open: 0, awaiting_worker: 0, awaiting_supervisor: 0,
    escalated: 0, resolved: 0, rejected: 0, auto_resolved: 0, stuck: 0,
  },
  overtime_limit_hours: 40,
  reasons: [],
  teams: [{ team: 'Inbound', status: 'ready', reasons: [] }],
  workers: [{
    employee_id: 'E001', employee_name: 'Amit Verma', team: 'Inbound', status: 'ready',
    worked_hours: 20, scheduled_remaining_hours: 0, projected_hours: 20, reasons: [],
  }],
}

const missing: ReadinessReason = {
  employee_id: 'E001', code: 'active_case', message: 'Missing clock-out', blocking: true,
  exception_ids: ['P1-E001-2026-04-14'], owner_id: 'E101', owner_name: 'Ravi Kumar',
  contact: 'worker',
}
const signed: PayrollReadiness = {
  ...closed, can_sign: false, can_reopen: true,
  signoff: {
    signer_name: 'Priya Sharma', signed_at: '2026-04-16T08:00:00', note: 'Reviewed attendance',
    reopened_at: null, stale: false,
  },
}

describe('Payroll readiness', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('shows loading, open-week blockers, and case links', async () => {
    vi.spyOn(api, 'getPayroll').mockResolvedValue({
      ...closed, week_start: '2026-04-13', week_end: '2026-04-19', closed: false,
      can_sign: false, status: 'blocked', reasons: [missing],
    })
    render(<PayrollPage />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading payroll readiness')
    expect(await screen.findByRole('heading', { name: 'Blocked' })).toBeInTheDocument()
    expect(screen.getByText(/In progress · sign-off unavailable/)).toBeInTheDocument()
    expect(screen.getByText(/Next: Ravi Kumar/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'P1-E001-2026-04-14' }))
      .toHaveAttribute('href', '/admin?case=P1-E001-2026-04-14')
    expect(screen.queryByRole('button', { name: 'Sign off week' })).not.toBeInTheDocument()
  })

  it('shows errors and retries into an empty state', async () => {
    const read = vi.spyOn(api, 'getPayroll')
      .mockRejectedValueOnce(new api.ApiError(403, 'supervisor_only', 'Reviewer access required'))
      .mockResolvedValueOnce({ ...closed, has_data: false, can_sign: false })
    render(<PayrollPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Reviewer access required')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'No attendance data' })).toBeInTheDocument()
    expect(read).toHaveBeenCalledTimes(2)
  })

  it('selects a week and confirms sign-off and reopen', async () => {
    const read = vi.spyOn(api, 'getPayroll').mockResolvedValue(closed)
    const sign = vi.spyOn(api, 'signPayroll').mockResolvedValue(signed)
    const reopen = vi.spyOn(api, 'reopenPayroll').mockResolvedValue({
      ...closed, signoff: { ...signed.signoff!, reopened_at: '2026-04-16T09:00:00' },
    })
    render(<PayrollPage />)
    await screen.findByRole('heading', { name: 'Ready' })
    fireEvent.change(screen.getByLabelText('Week starting Monday'), { target: { value: closed.week_start } })
    await userEvent.click(screen.getByRole('button', { name: 'View week' }))
    expect(read).toHaveBeenLastCalledWith(closed.week_start, 'E201', expect.any(AbortSignal))

    await userEvent.click(await screen.findByRole('button', { name: 'Sign off week' }))
    expect(sign).not.toHaveBeenCalled()
    await userEvent.type(screen.getByLabelText('Sign-off note (optional)'), 'Reviewed attendance')
    await userEvent.click(screen.getByRole('button', { name: 'Confirm sign-off' }))
    expect(sign).toHaveBeenCalledWith(closed.week_start, 'E201', 'Reviewed attendance')
    expect(screen.getByRole('status')).toHaveTextContent('Signed off · Priya Sharma')

    await userEvent.click(screen.getByRole('button', { name: 'Reopen week' }))
    expect(screen.getByRole('button', { name: 'Confirm reopen' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Reason to reopen'), 'Recheck the attendance')
    await userEvent.click(screen.getByRole('button', { name: 'Confirm reopen' }))
    expect(reopen).toHaveBeenCalledWith(closed.week_start, 'E201', 'Recheck the attendance')
    expect(screen.getByRole('status')).toHaveTextContent('Reopened · Priya Sharma')
  })

  it('renders team readiness without sign-off controls', async () => {
    vi.spyOn(api, 'getPayroll').mockResolvedValue({
      ...closed, scope: 'team', can_sign: false, status: 'ready_with_notes',
      reasons: [{ ...missing, blocking: false }],
    })
    render(<PayrollPage />)
    expect(await screen.findByRole('heading', { name: 'Ready with notes' })).toBeInTheDocument()
    expect(screen.getByText(/Your team/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign off week' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reopen week' })).not.toBeInTheDocument()
  })
})
