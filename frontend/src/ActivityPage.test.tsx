import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ActivityPage, whenText } from './ActivityPage'
import {
  ApiError,
  getActivity,
  getActivitySummary,
  getAdminCase,
  getAutonomy,
  type ActivityFeed,
  type ActivityItem,
  type ActivitySummary,
  type AutonomyRow,
} from './api'

vi.mock('./api', async (importOriginal) => ({
  ...await importOriginal<typeof import('./api')>(),
  getActivity: vi.fn(),
  getActivitySummary: vi.fn(),
  getAutonomy: vi.fn(),
  getAdminCase: vi.fn(),
}))

const NEHA_P1 = 'P1-E004-2026-04-15'

function event(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    id: 40,
    at: '2026-04-17T08:00:00',
    actor_type: 'system',
    actor_label: 'System',
    actor_name: 'No-reply ladder',
    autonomous: true,
    action: 'no_reply_to_supervisor',
    capability: 'no_reply_to_supervisor',
    sentence: 'No reply for 24 h: brought in Ravi Kumar. Nothing was changed.',
    reason: null,
    case: {
      exception_id: NEHA_P1,
      policy_id: 'P1',
      date: '2026-04-15',
      title: 'Every shift needs a clock-in and a clock-out',
      status: 'awaiting_supervisor',
    },
    employee: { employee_id: 'E004', name: 'Neha Gupta', team: 'Inbound' },
    ...overrides,
  }
}

const punch = event({
  id: 12,
  at: '2026-04-16T08:00:00',
  actor_type: 'device',
  actor_label: 'Device',
  actor_name: 'DEMO-SIM',
  action: 'punch_ingested',
  capability: 'device_punch',
  sentence: 'DEMO-SIM recorded a in for Neha Gupta at Wed 15 Apr 08:58.',
  case: null,
})
const undo = event({
  id: 50,
  at: '2026-04-18T08:00:00',
  actor_type: 'supervisor',
  actor_label: 'Supervisor',
  actor_name: 'Ravi Kumar',
  autonomous: false,
  action: 'auto_resolve_undone',
  capability: 'undo_auto_resolve',
  sentence: 'Ravi Kumar undid the auto-resolve, 1 punch(es) restored; the case is open again.',
  reason: 'Sana says the second tap was a real re-entry',
  case: { ...event().case!, exception_id: 'P2-E005-2026-04-13-P0003', policy_id: 'P2' },
  employee: { employee_id: 'E005', name: 'Sana Iqbal', team: 'Inbound' },
})

function feed(items: ActivityItem[], next: number | null = null): ActivityFeed {
  return { viewer: { employee_id: 'E201', role: 'payroll_admin' }, items, next_before_id: next }
}

function summary(overrides: Partial<ActivitySummary['counts']> = {}): ActivitySummary {
  return {
    date_from: null,
    date_to: null,
    counts: {
      investigated: 4, messages_sent: 2, reminders_sent: 2, auto_resolved: 1,
      auto_resolves_undone: 1, escalated_by_silence: 1, human_approvals: 1,
      decided_without_worker: 0, human_rejections: 0, device_punches: 1,
      ...overrides,
    },
    definitions: {},
  }
}

const rows: AutonomyRow[] = [
  {
    key: 'auto_resolve', title: 'Auto-resolve a low-risk exception', kind: 'allowed',
    actor_type: 'code', actor_label: 'Code', performed_by: 'Rule engine', approval: 'none',
    approval_label: 'None', reversible: 'yes_undo', reversible_label: 'Yes, with undo',
    guardrail: 'Only P2 (duplicate tap) and P7 (late within grace).', autonomous: true,
    audit_actions: ['auto_resolve'], proof_tests: [],
  },
  {
    key: 'never_llm_writes', title: 'Write timecards, schedules or leave', kind: 'never',
    actor_type: 'llm_agent', actor_label: 'LLM agent', performed_by: 'LLM agent', approval: 'none',
    approval_label: 'None', reversible: 'not_applicable', reversible_label: 'Not applicable',
    guardrail: 'Its tools are read-only.', autonomous: false, audit_actions: [], proof_tests: [],
  },
]

describe('activity center', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(getActivitySummary).mockResolvedValue(summary())
    vi.mocked(getAutonomy).mockResolvedValue(rows)
  })

  it('formats workflow time without a timezone shift', () => {
    expect(whenText('2026-04-17T08:00:00')).toBe('Fri 17 Apr, 08:00')
  })

  it('shows the summary strip and the feed, newest first, with actors and reasons', async () => {
    vi.mocked(getActivity).mockResolvedValue(feed([undo, event(), punch]))
    render(<ActivityPage />)
    const list = await screen.findByRole('list', { name: 'Events, newest first' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('Ravi Kumar undid the auto-resolve')
    expect(items[0]).toHaveTextContent('Reason: Sana says the second tap was a real re-entry')
    expect(items[1]).toHaveTextContent('No-reply ladder')
    expect(items[2]).toHaveTextContent('Device')
    expect(items[2]).toHaveTextContent('Neha Gupta')
    expect(screen.getByLabelText('Escalated by silence: 1')).toBeInTheDocument()
    expect(screen.getByLabelText('Auto-resolved: 1')).toHaveTextContent('(1 undone)')
    expect(screen.getByLabelText('Device punches: 1')).toBeInTheDocument()
  })

  it('sends each filter to the API, and the case box as employee or case ID', async () => {
    vi.mocked(getActivity).mockResolvedValue(feed([event()]))
    const user = userEvent.setup()
    render(<ActivityPage />)
    await screen.findByRole('list', { name: 'Events, newest first' })
    await user.selectOptions(screen.getByLabelText('Show'), 'autonomous')
    await user.selectOptions(screen.getByLabelText('Who'), 'device')
    await user.selectOptions(screen.getByLabelText('Policy'), 'P1')
    await user.type(screen.getByLabelText('Case or employee'), 'e004{Enter}')
    await waitFor(() => expect(getActivity).toHaveBeenLastCalledWith(
      { mode: 'autonomous', actor_type: 'device', policy_id: 'P1', employee_id: 'E004' },
      'E201',
      expect.anything(),
    ))
    expect(getActivitySummary).toHaveBeenLastCalledWith(
      expect.objectContaining({ policy_id: 'P1', employee_id: 'E004' }), 'E201', expect.anything(),
    )
    await user.clear(screen.getByLabelText('Case or employee'))
    await user.type(screen.getByLabelText('Case or employee'), `${NEHA_P1}{Enter}`)
    await waitFor(() => expect(getActivity).toHaveBeenLastCalledWith(
      expect.objectContaining({ exception_id: NEHA_P1 }), 'E201', expect.anything(),
    ))
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(getActivity).toHaveBeenLastCalledWith({}, 'E201', expect.anything()))
  })

  it('loads older pages with before_id', async () => {
    vi.mocked(getActivity)
      .mockResolvedValueOnce(feed([event()], 40))
      .mockResolvedValueOnce(feed([punch]))
    const user = userEvent.setup()
    render(<ActivityPage />)
    await user.click(await screen.findByRole('button', { name: 'Load older' }))
    expect(getActivity).toHaveBeenLastCalledWith({ before_id: 40 })
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(2))
    expect(screen.queryByRole('button', { name: 'Load older' })).not.toBeInTheDocument()
  })

  it('shows the empty state', async () => {
    vi.mocked(getActivity).mockResolvedValue(feed([]))
    vi.mocked(getActivitySummary).mockResolvedValue(summary({ investigated: 0 }))
    render(<ActivityPage />)
    expect(await screen.findByText('Nothing has happened yet.')).toBeInTheDocument()
  })

  it('explains a refusal in plain words', async () => {
    vi.mocked(getActivity).mockRejectedValue(new ApiError(403, 'supervisor_only', 'only reviewers'))
    render(<ActivityPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Only supervisors and the payroll admin can see the activity.',
    )
  })

  it('opens the existing case detail from a feed row', async () => {
    vi.mocked(getActivity).mockResolvedValue(feed([event()]))
    vi.mocked(getAdminCase).mockReturnValue(new Promise(() => {}))
    const user = userEvent.setup()
    render(<ActivityPage />)
    await user.click(await screen.findByRole('button', { name: `Open case ${NEHA_P1}` }))
    expect(getAdminCase).toHaveBeenCalledWith(NEHA_P1, expect.anything())
  })

  it('shows the autonomy table with its never rows', async () => {
    vi.mocked(getActivity).mockResolvedValue(feed([]))
    const user = userEvent.setup()
    render(<ActivityPage />)
    await user.click(screen.getByRole('tab', { name: 'Autonomy' }))
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Auto-resolve a low-risk exception')).toBeInTheDocument()
    expect(within(table).getByText('Yes, with undo')).toBeInTheDocument()
    expect(within(table).queryByText('Write timecards, schedules or leave')).not.toBeInTheDocument()
    expect(screen.getByText(/LLM agent: never/).closest('li')).toHaveTextContent(
      'LLM agent: never write timecards, schedules or leave.',
    )
    expect(screen.getByRole('tab', { name: 'Autonomy' })).toHaveAttribute('aria-selected', 'true')
  })
})
