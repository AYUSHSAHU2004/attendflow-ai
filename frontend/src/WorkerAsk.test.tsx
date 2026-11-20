import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { askQuestion, getAskHistory, type AskHistory, type AskResult } from './api'
import { SUGGESTIONS, WorkerAsk } from './WorkerAsk'

vi.mock('./api', () => ({
  askQuestion: vi.fn(),
  getAskHistory: vi.fn(),
}))

const limits = {
  max_chars: 300,
  questions_per_hour: 10,
  questions_left_this_hour: 9,
  retry_after_seconds: null,
  llm_configured: true,
  llm_calls_left_today: 57,
}
const empty: AskHistory = { items: [], limits }

function result(overrides: Partial<AskResult> = {}): AskResult {
  return {
    question_id: 1,
    question: 'Why was my punch on Tuesday flagged?',
    kind: 'answer',
    source: 'llm',
    label: 'AI answer',
    reason: 'validated',
    refusal_code: null,
    answer: 'P1-E001-2026-04-14 is open: you clocked in at 09:00 and there is no clock-out.',
    sources: [
      {
        kind: 'case', id: 'P1-E001-2026-04-14', label: 'P1 · 2026-04-14',
        text: 'Clock-in 09:00, no clock-out. Your supervisor is reviewing it', in_history: true,
      },
      {
        kind: 'policy', id: 'P1', label: 'P1: Every shift needs a clock-in and a clock-out',
        text: '## P1: Every shift needs a clock-in and a clock-out\n\n**Rule:** Every worked shift must have one clock-in.',
      },
      { kind: 'punches', id: null, label: 'Your punches' },
    ],
    intents: ['my_cases', 'my_punches'],
    asked_at: '2026-04-16T08:00:00',
    llm_calls: 1,
    latency_ms: 2400,
    limits: { ...limits, questions_left_this_hour: 8 },
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

describe('worker Ask tab', () => {
  beforeEach(() => vi.resetAllMocks())

  it('loads only the history on open, counts characters and offers suggestions', async () => {
    vi.mocked(getAskHistory).mockResolvedValue(empty)
    const user = userEvent.setup()
    render(<WorkerAsk />)
    expect(await screen.findByText('9 questions left this hour.')).toBeVisible()
    expect(askQuestion).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    await user.type(screen.getByLabelText('Ask about your attendance'), 'My shifts?')
    expect(screen.getByText('10 / 300')).toBeVisible()
    expect(screen.getByLabelText('Ask about your attendance')).toHaveAttribute('maxLength', '300')
    expect(SUGGESTIONS.length).toBeGreaterThanOrEqual(4)
    for (const text of SUGGESTIONS) expect(screen.getByRole('button', { name: text })).toBeVisible()
  })

  it('shows a loading state, then the AI answer with source chips', async () => {
    vi.mocked(getAskHistory).mockResolvedValue(empty)
    const pending = deferred<AskResult>()
    vi.mocked(askQuestion).mockReturnValue(pending.promise)
    const opened: string[] = []
    const user = userEvent.setup()
    render(<WorkerAsk onOpenCase={(id) => opened.push(id)} />)
    await user.click(await screen.findByRole('button', { name: SUGGESTIONS[1] }))
    expect(askQuestion).toHaveBeenCalledWith(SUGGESTIONS[1])
    expect(screen.getByRole('status')).toHaveTextContent('Checking your records')
    pending.resolve(result())
    const card = await screen.findByRole('article', { name: 'Answer' })
    expect(within(card).getByText('AI answer')).toBeVisible()
    expect(within(card).getByText(/is open: you clocked in at 09:00/)).toBeVisible()
    await user.click(within(card).getByRole('button', { name: /P1: Every shift/ }))
    expect(within(card).getByRole('region')).toHaveTextContent('Rule: Every worked shift must have one clock-in.')
    await user.click(within(card).getByRole('button', { name: /P1 · 2026-04-14/ }))
    expect(opened).toEqual(['P1-E001-2026-04-14'])
    expect(within(card).getByText('Your punches')).toBeVisible()
    expect(screen.getByText('8 questions left this hour.')).toBeVisible()
  })

  it('labels a template answer', async () => {
    vi.mocked(getAskHistory).mockResolvedValue(empty)
    vi.mocked(askQuestion).mockResolvedValue(result({
      source: 'template', label: 'Template answer', reason: 'validation_failed',
      answer: 'You have 11 days of sick leave left (1 used of 12 this year).',
      sources: [{ kind: 'leave_balance', id: null, label: 'Your leave balance' }],
    }))
    const user = userEvent.setup()
    render(<WorkerAsk />)
    await user.type(await screen.findByLabelText('Ask about your attendance'), 'How many sick days do I have left?')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    const card = await screen.findByRole('article', { name: 'Answer' })
    expect(within(card).getByText('Template answer')).toBeVisible()
    expect(within(card).getByText(/the AI answer was not used/)).toBeVisible()
  })

  it('shows a plain "I can\'t answer that" for a refusal, without sources', async () => {
    vi.mocked(getAskHistory).mockResolvedValue(empty)
    vi.mocked(askQuestion).mockResolvedValue(result({
      kind: 'refusal', source: 'refusal', label: "Can't answer", reason: 'refused',
      refusal_code: 'other_person', sources: [],
      answer: "I can't answer that: I only answer questions about your own attendance, never about other people.",
    }))
    const user = userEvent.setup()
    render(<WorkerAsk />)
    await user.type(await screen.findByLabelText('Ask about your attendance'), 'What is Neha’s salary?')
    await user.keyboard('{Enter}')
    const card = await screen.findByRole('article', { name: 'I can’t answer that' })
    expect(within(card).getByText("Can't answer")).toBeVisible()
    expect(within(card).queryByText('Sources')).not.toBeInTheDocument()
  })

  it('explains the hourly limit and keeps the typed question', async () => {
    vi.mocked(getAskHistory).mockResolvedValue(empty)
    vi.mocked(askQuestion).mockRejectedValue(Object.assign(new Error('You have asked a lot of questions this hour.'), {
      code: 'qa_rate_limited', status: 429, details: { retry_after_seconds: 600 },
    }))
    const user = userEvent.setup()
    render(<WorkerAsk />)
    const box = await screen.findByLabelText('Ask about your attendance')
    await user.type(box, 'Who is my supervisor?')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Please try again in about 10 minutes.')
    expect(box).toHaveValue('Who is my supervisor?')
  })

  it('shows other errors plainly', async () => {
    vi.mocked(getAskHistory).mockRejectedValue(new Error('Request failed (500).'))
    vi.mocked(askQuestion).mockRejectedValue(new Error('Request failed (502).'))
    const user = userEvent.setup()
    render(<WorkerAsk />)
    expect(await screen.findByText('Request failed (500).')).toBeVisible()
    await user.click(screen.getByRole('button', { name: SUGGESTIONS[0] }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Request failed (502).')
  })

  it('lists earlier questions from the history', async () => {
    vi.mocked(getAskHistory).mockResolvedValue({
      items: [result({ question_id: 7, question: 'What is the late-arrival rule?', sources: [] })],
      limits,
    })
    render(<WorkerAsk />)
    const earlier = await screen.findByRole('region', { name: 'Earlier questions' })
    expect(within(earlier).getByText('You asked: “What is the late-arrival rule?”')).toBeVisible()
  })
})
