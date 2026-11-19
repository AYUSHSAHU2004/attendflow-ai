import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getDashboard, type Dashboard } from './api'
import { DashboardPage } from './DashboardPage'

vi.mock('./api', async (importOriginal) => ({
  ...await importOriginal<typeof import('./api')>(),
  getDashboard: vi.fn(),
}))

const example: Dashboard = {
  scope: 'all',
  workflow_now: '2026-04-16T16:00:00',
  active_total: 16,
  stuck: 1,
  by_status: { open: 15, awaiting_worker: 1, awaiting_supervisor: 0, escalated: 0 },
  by_severity: { high: 8, medium: 6, low: 2 },
  by_policy: { P1: 2, P5: 1 },
  ladder: { waiting: 0, reminded: 1, supervisor: 0, payroll_admin: 0 },
  aging: { limits_hours: [8, 24, 48], case_age: [0, 16, 0, 0], waiting_age: [0, 1, 0, 0] },
  workload: [{ supervisor_id: 'E101', supervisor_name: 'Ravi Kumar', active: 16,
    awaiting_worker: 1, awaiting_supervisor: 0 }],
  overtime: {
    week_start: '2026-04-13', week_end: '2026-04-19', limit_hours: 40, warning_margin_hours: 4,
    workers: [
      { employee_id: 'E002', employee_name: 'Meena Rao', worked_hours: 36,
        scheduled_remaining_hours: 12, projected_hours: 48, level: 'projected_over' },
    ],
  },
  auto_resolve: {
    resolved_without_human: 1, needed_handling: 17, percent: 5.9, undone: 0,
    closed_by_data_change: 0, date_from: null, date_to: null,
    auto_resolve_enabled: true, allowed_policies: ['P2', 'P7'], by_policy: [],
  },
}

describe('Operations dashboard', () => {
  beforeEach(() => vi.resetAllMocks())

  it('renders the requested panels and links to the matching admin filters', async () => {
    vi.mocked(getDashboard).mockResolvedValue(example)
    render(<DashboardPage />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading operations dashboard')
    const work = await screen.findByRole('region', { name: 'Open work' })
    expect(within(work).getByRole('link', { name: 'High' })).toHaveAttribute(
      'href', '/admin?severity=high&active_only=true',
    )
    expect(within(work).getByRole('link', { name: 'Reminder sent' })).toHaveAttribute(
      'href', '/admin?no_reply=reminded&active_only=true',
    )
    expect(within(work).getByRole('link', { name: '1 stuck on no reply' })).toHaveAttribute(
      'href', '/admin?no_reply=any',
    )
    const policy = screen.getByRole('region', { name: 'Open work by policy' })
    expect(within(policy).getByRole('link', { name: 'P5' })).toHaveAttribute(
      'href', '/admin?policy_id=P5&active_only=true',
    )
    expect(screen.getByRole('region', { name: 'Case aging' })).toHaveTextContent('8 to under 24 h')
    expect(screen.getByRole('region', { name: 'Team workload' })).toHaveTextContent('Ravi Kumar')
    const risk = screen.getByRole('region', { name: 'Weekly overtime risk' })
    expect(risk).toHaveTextContent('48 h')
    expect(risk).toHaveTextContent('Projected over')
    expect(screen.getByRole('region', { name: 'Resolved without a human' })).toHaveTextContent(
      '1 of 17 exceptions resolved without a human',
    )
  })

  it('shows an empty date range and can retry a failed request', async () => {
    vi.mocked(getDashboard).mockRejectedValueOnce(new Error('Offline'))
      .mockResolvedValue({
        ...example, active_total: 0, by_policy: {}, overtime: { ...example.overtime, workers: [] },
      })
    const user = userEvent.setup()
    render(<DashboardPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Offline')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('No active exceptions in this date range.')).toBeVisible()
    expect(screen.getByText('No workers are near or above the limit.')).toBeVisible()
  })

  it('uses the team view without sending supervisors to the admin list', async () => {
    vi.mocked(getDashboard).mockResolvedValue({ ...example, scope: 'team' })
    render(<DashboardPage />)
    expect(await screen.findByRole('link', { name: 'Decision queue' })).toBeVisible()
    expect(screen.queryByRole('link', { name: 'High' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'All exceptions' })).toBeNull()
  })

  it('passes the selected exception date to the API and drill-down links', async () => {
    vi.mocked(getDashboard).mockResolvedValue(example)
    const user = userEvent.setup()
    render(<DashboardPage />)
    await screen.findByRole('region', { name: 'Open work' })
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-04-14' } })
    await user.click(screen.getByRole('button', { name: 'Apply dates' }))
    expect(getDashboard).toHaveBeenLastCalledWith(
      { date_from: '2026-04-14', date_to: undefined }, 'E201', expect.any(AbortSignal),
    )
    expect(await screen.findByRole('link', { name: 'High' })).toHaveAttribute(
      'href', '/admin?date_from=2026-04-14&severity=high&active_only=true',
    )
  })
})
