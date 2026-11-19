import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminPage } from './AdminPage'
import {
  ApiError,
  getAdminCase,
  getAdminOverview,
  getAutoResolveMetric,
  getQueue,
  getSchedulerStatus,
  getTeamAutoFixes,
  undoAutoResolve,
  type AdminCase,
  type AdminOverview,
  type UndoResult,
} from './api'
import { AutoFixPanel, AutoResolveMetricLine } from './AutoFix'
import { SupervisorPage } from './SupervisorPage'
import { autoFix, metric, schedulerStatus } from './testFixtures'

vi.mock('./api', async (importOriginal) => ({
  ...await importOriginal<typeof import('./api')>(),
  getAdminOverview: vi.fn(),
  getAdminCase: vi.fn(),
  getAutoResolveMetric: vi.fn(),
  getSchedulerStatus: vi.fn(),
  getQueue: vi.fn(),
  getTeamAutoFixes: vi.fn(),
  undoAutoResolve: vi.fn(),
}))

const SANA_P2 = 'P2-E005-2026-04-13-P0003'
const REASON = 'Checking the second tap with the worker'

function overview(): AdminOverview {
  return {
    counters: {
      total: 17, open: 16, awaiting_worker: 0, awaiting_supervisor: 0, escalated: 0,
      resolved: 1, rejected: 0, auto_resolved: 1, stuck: 0,
    },
    matched: 2,
    limit: 200,
    offset: 0,
    items: [
      {
        exception_id: SANA_P2, employee_id: 'E005', employee_name: 'Sana Khan', team: 'Inbound',
        date: '2026-04-13', policy_id: 'P2', title: 'Duplicate punches are merged',
        summary: "2 'in' taps within 2 min", severity: 'low', kind: 'breach', status: 'resolved',
        auto_resolved: true, auto_resolve_undone: false, assigned_to: 'E101',
        assigned_to_name: 'Ravi Kumar', investigated: false, who_to_ask: null,
        investigation_fallback: null, needs_your_decision: false, updated_at: '2026-04-16T08:00:00',
      },
      {
        exception_id: 'P7-E004-2026-04-15-late', employee_id: 'E004', employee_name: 'Neha Gupta',
        team: 'Inbound', date: '2026-04-15', policy_id: 'P7', title: 'Late arrival grace period',
        summary: 'Clock-in 2 min after the start', severity: 'low', kind: 'breach', status: 'open',
        auto_resolved: false, auto_resolve_undone: true, assigned_to: 'E101',
        assigned_to_name: 'Ravi Kumar', investigated: false, who_to_ask: null,
        investigation_fallback: null, needs_your_decision: false, updated_at: '2026-04-16T08:00:00',
      },
    ],
    filter_options: {
      statuses: ['open', 'awaiting_worker', 'awaiting_supervisor', 'escalated', 'resolved', 'rejected'],
      policy_ids: ['P2', 'P7'], teams: ['Inbound'], employees: [], severities: ['high', 'medium', 'low'],
    },
  }
}

function sanaCase(overrides: Partial<AdminCase> = {}): AdminCase {
  return {
    exception_id: SANA_P2, status: 'resolved', assigned_to: 'E101', assigned_to_name: 'Ravi Kumar',
    needs_your_decision: false, can_investigate: false, auto_resolved: true, auto_fix: autoFix(),
    employee: { employee_id: 'E005', name: 'Sana Khan', team: 'Inbound' }, date: '2026-04-13',
    policy_id: 'P2', title: 'Duplicate punches are merged', summary: "2 'in' taps within 2 min",
    severity: 'low', kind: 'breach', details: {},
    policy: { policy_id: 'P2', title: 'Duplicate punches are merged', rule: 'r', cited_text: 'r' },
    evidence: [], options: [], investigation: null, latest_job: null, worker_messages: [],
    recheck: null, applied_fix: { action: 'auto_resolve' }, audit_trail: [], tool_calls: [],
    ...overrides,
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getAdminOverview).mockResolvedValue(overview())
  vi.mocked(getAdminCase).mockResolvedValue(sanaCase())
  vi.mocked(getAutoResolveMetric).mockResolvedValue(metric())
  vi.mocked(getSchedulerStatus).mockResolvedValue(schedulerStatus())
  vi.mocked(getQueue).mockResolvedValue([])
  vi.mocked(getTeamAutoFixes).mockResolvedValue([])
})

describe('the resolved-without-a-human metric', () => {
  it('shows X of Y, the percentage and the per-policy line', async () => {
    render(<AutoResolveMetricLine refresh={0} />)
    const region = await screen.findByRole('region', { name: 'Resolved without a human' })
    expect(region).toHaveTextContent('1 of 17 exceptions resolved without a human (5.9%)')
    expect(region).toHaveTextContent('P2: 1 auto-resolved')
    expect(region).not.toHaveTextContent('Not counted')
  })

  it('explains the excluded cases in a footnote and shows undone ones', async () => {
    vi.mocked(getAutoResolveMetric).mockResolvedValue(metric({
      resolved_without_human: 1, needed_handling: 18, percent: 5.6, undone: 1, closed_by_data_change: 1,
      by_policy: [
        { policy_id: 'P2', needed_handling: 1, auto_resolved: 1, undone: 0, closed_by_data_change: 0 },
        { policy_id: 'P7', needed_handling: 1, auto_resolved: 0, undone: 1, closed_by_data_change: 0 },
      ],
    }))
    render(<AutoResolveMetricLine refresh={0} />)
    const region = await screen.findByRole('region', { name: 'Resolved without a human' })
    expect(region).toHaveTextContent('1 of 18')
    expect(region).toHaveTextContent('P7: 0 auto-resolved, 1 undone')
    expect(region).toHaveTextContent('Not counted: 1 case closed because the data changed')
  })

  it('says when the kill switch is off', async () => {
    vi.mocked(getAutoResolveMetric).mockResolvedValue(metric({
      resolved_without_human: 0, percent: 0, auto_resolve_enabled: false, by_policy: [],
    }))
    render(<AutoResolveMetricLine refresh={0} />)
    expect(await screen.findByText(/Auto-resolve is switched off/)).toBeVisible()
  })

  it('sits on /admin next to a consistent Auto-resolved tile', async () => {
    render(<AdminPage />)
    const region = await screen.findByRole('region', { name: 'Resolved without a human' })
    expect(region).toHaveTextContent('1 of 17')
    const counters = screen.getByRole('region', { name: 'Counters' })
    expect(within(counters).getByRole('button', { name: 'Auto-resolved: 1' })).toBeVisible()
  })
})

describe('auto-resolved cases on /admin', () => {
  it('labels auto-resolved and undone rows', async () => {
    render(<AdminPage />)
    const rows = await screen.findAllByRole('row')
    expect(within(rows[1]).getByText('auto')).toBeVisible()
    expect(within(rows[2]).getByText('undone')).toBeVisible()
  })

  it('explains the fix and undoes it with a reason', async () => {
    const user = userEvent.setup()
    vi.mocked(undoAutoResolve).mockResolvedValue({ restored: [{ punch_id: 'P0005' }] } as unknown as UndoResult)
    render(<AdminPage />)
    await user.click(await screen.findByRole('button', { name: `Open ${SANA_P2}` }))
    const panel = await screen.findByRole('region', { name: 'Auto-resolve' })
    expect(panel).toHaveTextContent('Auto-resolved by the system')
    expect(panel).toHaveTextContent("Why it was allowed: 2 'in' taps 2 min apart, within the 5 min duplicate window.")
    expect(panel).toHaveTextContent('P0005 clock-in 08:59: voided (kept in the database)')
    expect(panel).toHaveTextContent('Policy: Keep the earliest punch and void the later one.')

    await user.click(within(panel).getByRole('button', { name: 'Undo' }))
    const confirm = within(panel).getByRole('button', { name: 'Confirm undo' })
    await user.type(within(panel).getByRole('textbox'), 'too short')
    expect(confirm).toBeDisabled()
    vi.mocked(getAdminCase).mockResolvedValue(sanaCase({
      status: 'open', auto_resolved: false,
      auto_fix: autoFix({
        state: 'undone', can_undo: false, undone_by: 'E201', undone_by_name: 'Priya Sharma',
        undone_at: '2026-04-16T08:00:00', undo_reason: REASON,
      }),
    }))
    await user.clear(within(panel).getByRole('textbox'))
    await user.type(within(panel).getByRole('textbox'), REASON)
    await user.click(confirm)

    expect(undoAutoResolve).toHaveBeenCalledWith(SANA_P2, { reason: REASON }, 'E201')
    expect(await screen.findByText('Undone: 1 punch restored. The case is open for a person.')).toBeVisible()
    const after = await screen.findByRole('region', { name: 'Auto-resolve' })
    await waitFor(() => expect(after).toHaveTextContent('Undone by Priya Sharma'))
    expect(after).toHaveTextContent(REASON)
    expect(within(after).queryByRole('button', { name: 'Undo' })).toBeNull()
    await waitFor(() => expect(getAutoResolveMetric).toHaveBeenCalledTimes(2))  // the metric reloads
  })
})

describe('the Undo error state', () => {
  it('shows a refused undo in plain words and keeps the form', async () => {
    const user = userEvent.setup()
    vi.mocked(undoAutoResolve).mockRejectedValue(new ApiError(
      409, 'undo_conflict',
      'punch P0005 changed after the auto-resolve, so it cannot be restored exactly; decide this case by hand instead',
    ))
    const onUndone = vi.fn()
    render(<AutoFixPanel info={autoFix()} exceptionId={SANA_P2} actor="E101" onUndone={onUndone} />)
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    await user.type(screen.getByRole('textbox'), REASON)
    await user.click(screen.getByRole('button', { name: 'Confirm undo' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Undo refused, nothing was changed: punch P0005 changed after the auto-resolve',
    )
    expect(onUndone).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Confirm undo' })).toBeEnabled()
  })

  it('explains a team permission refusal', async () => {
    const user = userEvent.setup()
    vi.mocked(undoAutoResolve).mockRejectedValue(new ApiError(403, 'not_assigned', 'x'))
    render(<AutoFixPanel info={autoFix()} exceptionId={SANA_P2} actor="E102" onUndone={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    await user.type(screen.getByRole('textbox'), REASON)
    await user.click(screen.getByRole('button', { name: 'Confirm undo' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This worker is not on your team')
  })

  it('offers no Undo when the viewer may not undo or a person already did', () => {
    const { rerender } = render(
      <AutoFixPanel info={autoFix({ can_undo: false })} exceptionId={SANA_P2} actor="E102" onUndone={vi.fn()} />,
    )
    expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull()
    rerender(
      <AutoFixPanel
        info={autoFix({ state: 'held', can_undo: false, changes: [], held_because: ['the taps came from different devices'] })}
        exceptionId={SANA_P2} actor="E201" onUndone={vi.fn()}
      />,
    )
    expect(screen.getByRole('region', { name: 'Auto-resolve' })).toHaveTextContent(
      'Left for a person: the taps came from different devices.',
    )
  })
})

describe("the supervisor's team list", () => {
  it('lists the team cases and undoes as the supervisor', async () => {
    const user = userEvent.setup()
    vi.mocked(getTeamAutoFixes).mockResolvedValue([{
      exception_id: SANA_P2, employee_id: 'E005', employee_name: 'Sana Khan', date: '2026-04-13',
      policy_id: 'P2', title: 'Duplicate punches are merged', summary: "2 'in' taps within 2 min",
      status: 'resolved', auto_fix: autoFix(),
    }])
    vi.mocked(undoAutoResolve).mockResolvedValue({ restored: [] } as unknown as UndoResult)
    render(<SupervisorPage />)
    const region = await screen.findByRole('region', { name: 'Auto-resolved for my team' })
    expect(await within(region).findByText('Sana Khan')).toBeVisible()
    await user.click(within(region).getByRole('button', { name: 'Undo' }))
    await user.type(within(region).getByRole('textbox'), REASON)
    await user.click(within(region).getByRole('button', { name: 'Confirm undo' }))
    expect(undoAutoResolve).toHaveBeenCalledWith(SANA_P2, { reason: REASON }, 'E101')
    expect(await screen.findByText('Undone. Nothing to restore; the case is open for a person.')).toBeVisible()
    await waitFor(() => expect(getQueue).toHaveBeenCalledTimes(2))  // the queue reloads
  })

  it('shows the empty state', async () => {
    render(<SupervisorPage />)
    expect(await screen.findByText('Nothing was auto-resolved for your team.')).toBeVisible()
  })
})
