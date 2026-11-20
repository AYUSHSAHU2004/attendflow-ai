import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getBriefing, refreshBriefing, type Briefing } from './api'
import { BriefingCard } from './BriefingCard'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  getBriefing: vi.fn(),
  refreshBriefing: vi.fn(),
}))

const P5 = 'P5-E002-2026-04-13'
const P1 = 'P1-E001-2026-04-14'

function make(overrides: Partial<Briefing> = {}): Briefing {
  return {
    scope: 'all',
    team: null,
    source: 'llm',
    reason: 'validated',
    label: 'Written by the LLM from verified facts',
    stale: false,
    stored: true,
    briefing_id: 4,
    headline: '16 cases are active.',
    sections: [
      { key: 'blocking_payroll', title: 'Blocking payroll', bullets: [{ text: `${P5} blocks payroll.`, case_ids: [P5, P1] }] },
      { key: 'watch', title: 'Watch', bullets: [{ text: 'Meena Iyer has 48 projected hours.', case_ids: [] }] },
    ],
    team_lines: [{ team: 'Inbound', text: '11 active.' }],
    generated_at: '2026-04-16T08:00:00',
    facts_hash: 'a2c7913a2335',
    llm_calls: 1,
    latency_ms: 1400,
    failed_checks: [],
    refresh: { allowed: true, reason: null, retry_after_seconds: null, calls_left_today: 39, llm_configured: true },
    ...overrides,
  }
}

describe('briefing card', () => {
  beforeEach(() => vi.resetAllMocks())

  it('shows an LLM briefing with its label and clickable case IDs', async () => {
    vi.mocked(getBriefing).mockResolvedValue(make())
    const open = vi.fn()
    const user = userEvent.setup()
    render(<BriefingCard actor="E201" onOpenCase={open} />)
    expect(await screen.findByText('Written by the LLM from verified facts')).toBeVisible()
    expect(screen.getByText('16 cases are active.')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Blocking payroll' })).toBeVisible()
    // The ID in the text and the cited ID that the text does not mention are both links.
    await user.click(screen.getByRole('button', { name: `Open case ${P5}` }))
    await user.click(screen.getByRole('button', { name: `Open case ${P1}` }))
    expect(open.mock.calls).toEqual([[P5], [P1]])
    expect(screen.getByText(/1 LLM call/)).toBeVisible()
    expect(refreshBriefing).not.toHaveBeenCalled() // fresh facts: no automatic refresh
    expect(getBriefing).toHaveBeenCalledWith('E201', expect.any(AbortSignal))
  })

  it('labels the template and shows which checks failed', async () => {
    vi.mocked(getBriefing).mockResolvedValue(make({
      source: 'template', reason: 'validation_failed', label: 'Template (the LLM draft failed the checks)',
      failed_checks: ['ungrounded_number'], llm_calls: 2,
    }))
    render(<BriefingCard actor="E201" onOpenCase={vi.fn()} />)
    expect(await screen.findByText('Template (the LLM draft failed the checks)')).toBeVisible()
    expect(screen.getByText(/failed checks: ungrounded_number/)).toBeVisible()
  })

  it('refreshes once by itself when the facts changed, showing the refreshing state', async () => {
    vi.mocked(getBriefing).mockResolvedValue(make({
      source: 'template', reason: 'facts_changed', stale: true, stored: false,
      label: 'Template (facts changed since the last briefing)',
    }))
    let finish: (value: Briefing) => void = () => {}
    vi.mocked(refreshBriefing).mockReturnValue(new Promise((resolve) => { finish = resolve }))
    render(<BriefingCard actor="E201" onOpenCase={vi.fn()} />)
    expect(await screen.findByText('Writing a fresh briefing from the current facts…')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Writing…' })).toBeDisabled()
    finish(make({ headline: 'Fresh from the LLM.' }))
    expect(await screen.findByText('Fresh from the LLM.')).toBeVisible()
    expect(refreshBriefing).toHaveBeenCalledTimes(1)
  })

  it('does not refresh by itself without an LLM, and the button still works', async () => {
    const none = { allowed: true, reason: null, retry_after_seconds: null, calls_left_today: 40, llm_configured: false }
    vi.mocked(getBriefing).mockResolvedValue(make({
      source: 'template', reason: 'not_generated', stale: true, stored: false, refresh: none,
      label: 'Template (no briefing generated yet)',
    }))
    vi.mocked(refreshBriefing).mockResolvedValue(make({
      source: 'template', reason: 'llm_unavailable', label: 'Template (LLM unavailable)', refresh: none,
    }))
    const user = userEvent.setup()
    render(<BriefingCard actor="E101" onOpenCase={vi.fn()} />)
    await screen.findByText('Template (no briefing generated yet)')
    expect(refreshBriefing).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(await screen.findByText('Template (LLM unavailable)')).toBeVisible()
    expect(refreshBriefing).toHaveBeenCalledWith('E101')
  })

  it('shows a supervisor scope and explains a rate limit in plain words', async () => {
    vi.mocked(getBriefing).mockResolvedValue(make({ scope: 'team', team: 'Inbound' }))
    vi.mocked(refreshBriefing).mockRejectedValue(
      new ApiError(429, 'briefing_too_soon', 'Refresh is not available yet', { retry_after_seconds: 200 }),
    )
    const user = userEvent.setup()
    render(<BriefingCard actor="E101" onOpenCase={vi.fn()} />)
    expect(await screen.findByText('· Inbound team')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Your team' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Refresh is available again in 4 min.')
  })

  it('disables Refresh while the server says too soon', async () => {
    vi.mocked(getBriefing).mockResolvedValue(make({
      refresh: { allowed: false, reason: 'too_soon', retry_after_seconds: 61, calls_left_today: 39, llm_configured: true },
    }))
    render(<BriefingCard actor="E201" onOpenCase={vi.fn()} />)
    expect(await screen.findByRole('button', { name: 'Refresh' })).toBeDisabled()
    expect(screen.getByText('Refresh is available again in 2 min.')).toBeVisible()
  })

  it('shows a load error and retries', async () => {
    vi.mocked(getBriefing).mockRejectedValueOnce(new Error('The briefing could not be loaded.'))
    vi.mocked(getBriefing).mockResolvedValueOnce(make())
    const user = userEvent.setup()
    render(<BriefingCard actor="E201" onOpenCase={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('The briefing could not be loaded.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.getByText('16 cases are active.')).toBeVisible())
  })

  it('reloads by itself when another viewer is already writing the briefing', async () => {
    vi.mocked(getBriefing).mockResolvedValueOnce(make({
      source: 'template', reason: 'facts_changed', stale: true, stored: false,
      label: 'Template (facts changed since the last briefing)',
    }))
    vi.mocked(getBriefing).mockResolvedValueOnce(make({ headline: 'Written by the other tab.' }))
    vi.mocked(refreshBriefing).mockRejectedValue(new ApiError(409, 'briefing_busy', 'busy'))
    render(<BriefingCard actor="E201" onOpenCase={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('it appears here in a moment')
    expect(await screen.findByText('Written by the other tab.', {}, { timeout: 6000 })).toBeVisible()
    expect(refreshBriefing).toHaveBeenCalledTimes(1) // no second automatic refresh
  }, 10000)
})
