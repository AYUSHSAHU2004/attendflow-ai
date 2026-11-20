import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  askQuestion, confirmWorkerTime, getAskHistory, getWorkerHistory, getWorkerInbox, sendReply,
  submitManualTime, type WorkerHistoryItem, type WorkerMessage,
} from './api'
import { WorkerInbox } from './WorkerInbox'

vi.mock('./api', () => ({
  getWorkerInbox: vi.fn(),
  getWorkerHistory: vi.fn(),
  sendReply: vi.fn(),
  confirmWorkerTime: vi.fn(),
  submitManualTime: vi.fn(),
  askQuestion: vi.fn(),
  getAskHistory: vi.fn(),
}))

const item: WorkerMessage = {
  exception_id: 'P1-E001-2026-04-14',
  date: '2026-04-14',
  message: 'Hi Amit, your clock-out is missing. Did you leave at 18:00?',
  needs_actual_time: false,
  reply_prompt: 'What time did you actually leave, and why?',
}

describe('worker inbox', () => {
  beforeEach(() => vi.resetAllMocks())

  it('confirms Yes and removes the answered question', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [item], notices: [] })
    vi.mocked(sendReply).mockResolvedValue({
      exception_id: item.exception_id, confirmed: true, needs_actual_time: false,
    })
    const user = userEvent.setup()
    render(<WorkerInbox />)
    await user.click(await screen.findByRole('button', { name: 'Yes' }))
    expect(sendReply).toHaveBeenCalledWith(item.exception_id, { confirmed: true, text: undefined })
    expect(await screen.findByText('Confirmation sent. Your supervisor will review it.')).toBeVisible()
    expect(screen.queryByText(item.message)).not.toBeInTheDocument()
  })

  it('sends No with text and keeps the question visible', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [item], notices: [] })
    vi.mocked(sendReply).mockResolvedValue({
      exception_id: item.exception_id, confirmed: false, needs_actual_time: true,
    })
    const user = userEvent.setup()
    render(<WorkerInbox />)
    await user.click(await screen.findByRole('button', { name: 'No' }))
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    await user.type(screen.getByLabelText(item.reply_prompt), 'I left after the shift.')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(sendReply).toHaveBeenCalledWith(item.exception_id, {
      confirmed: false, text: 'I left after the shift.',
    })
    expect(await screen.findByText('Thanks. Your response was saved.')).toBeVisible()
    expect(screen.getByText(item.message)).toBeVisible()
    expect(screen.getByText(/question is still open/)).toBeVisible()
  })

  it('shows the empty inbox', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [], notices: [] })
    render(<WorkerInbox />)
    expect(await screen.findByText('Nothing needs your attention')).toBeVisible()
  })

  it('shows a load error and retries the inbox request', async () => {
    vi.mocked(getWorkerInbox).mockRejectedValueOnce(new Error('The inbox could not be loaded.'))
    vi.mocked(getWorkerInbox).mockResolvedValueOnce({ items: [], notices: [] })
    const user = userEvent.setup()
    render(<WorkerInbox />)
    expect(await screen.findByRole('alert')).toHaveTextContent('The inbox could not be loaded.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Nothing needs your attention')).toBeVisible()
  })

  it('shows the candidate after a No reply and confirms it', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [item], notices: [] })
    vi.mocked(sendReply).mockResolvedValue({
      exception_id: item.exception_id, confirmed: false, needs_actual_time: true,
      time_review: { stage: 'candidate', timestamp: '2026-04-14T19:30:00', approximate: true },
    })
    vi.mocked(confirmWorkerTime).mockResolvedValue({
      exception_id: item.exception_id, confirmed: false, needs_actual_time: false,
      time_review: { stage: 'confirmed', approximate: false, timestamp: '2026-04-14T19:30:00', impact_note: 'Ravi will review the new exceptions.' },
    })
    const user = userEvent.setup()
    render(<WorkerInbox />)
    await user.click(await screen.findByRole('button', { name: 'No' }))
    await user.type(screen.getByLabelText(item.reply_prompt), 'Left around 7:30ish')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    // The time is shown in bold, so match the whole sentence across its parts.
    expect(await screen.findByText((_, el) => el?.tagName === 'P'
      && /We understood you left at 19:30/.test(el.textContent ?? ''))).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(confirmWorkerTime).toHaveBeenCalledWith(item.exception_id)
    expect(await screen.findByText('19:30 sent to your supervisor. Ravi will review the new exceptions.')).toBeVisible()
  })

  it('lets the worker edit a stored candidate after reload', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ notices: [], items: [{
      ...item, needs_actual_time: true,
      time_review: { stage: 'candidate', approximate: false, timestamp: '2026-04-14T19:30:00' },
    }] })
    vi.mocked(submitManualTime).mockResolvedValue({
      exception_id: item.exception_id, confirmed: false, needs_actual_time: false,
      time_review: { stage: 'confirmed', approximate: false, timestamp: '2026-04-14T18:30:00' },
    })
    const user = userEvent.setup()
    render(<WorkerInbox />)
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    const timeInput = screen.getByLabelText('Exact clock-out time')
    expect(timeInput).toHaveValue('19:30')
    fireEvent.change(timeInput, { target: { value: '18:30' } })
    await user.click(screen.getByRole('button', { name: 'Send time' }))
    expect(submitManualTime).toHaveBeenCalledWith(item.exception_id, {
      time: '18:30', actual_date: item.date,
    })
    expect(await screen.findByText('18:30 sent to your supervisor.')).toBeVisible()
  })

  it('asks for an exact manual time when extraction has no candidate', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ notices: [], items: [{
      ...item, needs_actual_time: true, time_review: { stage: 'manual', approximate: false },
    }] })
    vi.mocked(submitManualTime).mockResolvedValue({
      exception_id: item.exception_id, confirmed: false, needs_actual_time: false,
      time_review: { stage: 'confirmed', approximate: false, timestamp: '2026-04-14T18:00:00' },
    })
    const user = userEvent.setup()
    render(<WorkerInbox />)
    const timeInput = await screen.findByLabelText('Exact clock-out time')
    expect(screen.getByRole('button', { name: 'Send time' })).toBeDisabled()
    fireEvent.change(timeInput, { target: { value: '18:00' } })
    await user.click(screen.getByRole('button', { name: 'Send time' }))
    expect(submitManualTime).toHaveBeenCalledWith(item.exception_id, { time: '18:00', actual_date: undefined })
    expect(await screen.findByText('18:00 sent to your supervisor.')).toBeVisible()
  })
  it('shows the reminder and that the supervisor now reviews it (still answerable)', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ notices: [], items: [{
      ...item,
      reminder: {
        text: "Reminder: we still need your answer about Tue 14 Apr. If we don't hear from you by Fri 17 Apr 08:00, your supervisor will review it using the records.",
        sent_at: '2026-04-16T16:00:00',
      },
      status_note: 'Your supervisor is now reviewing this. You can still answer.',
    }] })
    render(<WorkerInbox />)
    const reminder = await screen.findByRole('note')
    expect(reminder).toHaveTextContent('Reminder: we still need your answer about Tue 14 Apr.')
    expect(reminder).toHaveTextContent('your supervisor will review it using the records.')
    expect(screen.getByText('Your supervisor is now reviewing this. You can still answer.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Yes' })).toBeEnabled()
  })

  it('shows plain notices for cases decided without a reply or sent to payroll', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [], notices: [
      {
        exception_id: 'P1-E001-2026-04-14', date: '2026-04-14', kind: 'decided_without_reply',
        title: 'Decided without your reply', text: 'Set clock-out to 18:00.',
        reason: 'Worker unreachable; the gate log shows 18:00.', at: '2026-04-17T09:00:00',
      },
      {
        exception_id: 'P1-E004-2026-04-15', date: '2026-04-15', kind: 'with_payroll',
        title: 'With payroll', text: 'Payroll is handling this now. Please speak to your supervisor.',
      },
    ] })
    render(<WorkerInbox />)
    const decided = await screen.findByRole('article', { name: 'Decided without your reply' })
    expect(decided).toHaveTextContent('Set clock-out to 18:00.')
    expect(decided).toHaveTextContent('Reason: Worker unreachable; the gate log shows 18:00.')
    expect(screen.getByRole('article', { name: 'With payroll' }))
      .toHaveTextContent('Payroll is handling this now.')
    expect(screen.getByText('No open questions')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Yes' })).not.toBeInTheDocument()
  })

  it('greets the worker, numbers the questions and gives big Yes/No buttons', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [item, { ...item, exception_id: 'P13-E001-2026-04-15', date: '2026-04-15' }], notices: [] })
    render(<WorkerInbox actor={{ id: 'E001', name: 'Amit Verma' }} />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Hi Amit' })).toBeVisible()
    expect(screen.getByText('Question 1 of 2')).toBeVisible()
    expect(screen.getByText('Question 2 of 2')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Questions (2)' })).toHaveAttribute('aria-pressed', 'true')
    const [yes] = screen.getAllByRole('button', { name: 'Yes' })
    expect(yes.parentElement).toHaveClass('yes-no') // the two-column, 3.5rem-tall button row
    // Each card is labelled by its own question, so a screen reader announces it.
    expect(screen.getAllByRole('article', { name: item.message })).toHaveLength(2)
  })

  it('moves focus to a clear confirmation after a reply and links to the history', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [item], notices: [] })
    vi.mocked(sendReply).mockResolvedValue({
      exception_id: item.exception_id, confirmed: true, needs_actual_time: false,
    })
    vi.mocked(getWorkerHistory).mockResolvedValue([])
    const user = userEvent.setup()
    render(<WorkerInbox actor={{ id: 'E001', name: 'Amit Verma' }} />)
    await user.click(await screen.findByRole('button', { name: 'Yes' }))
    const title = await screen.findByRole('heading', { name: /Thanks, Amit. Your answer is saved./ })
    expect(title).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'See my history' }))
    expect(await screen.findByText('No history yet')).toBeVisible()
    expect(screen.getByRole('button', { name: 'My history' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('the time field suits a phone keyboard', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ notices: [], items: [{
      ...item, needs_actual_time: true, time_review: { stage: 'manual', approximate: false },
    }] })
    render(<WorkerInbox />)
    const input = await screen.findByLabelText('Exact clock-out time')
    expect(input).toHaveAttribute('type', 'time')
    expect(input).toHaveAttribute('enterkeyhint', 'send')
    expect(input).toHaveAccessibleDescription('Use the 24-hour time, for example 18:30.')
  })

  it('shows what happened to each case in plain words, not by colour alone', async () => {
    const history: WorkerHistoryItem[] = [
      {
        exception_id: 'P1-E001-2026-04-14', date: '2026-04-14', updated_at: '2026-04-17T09:00:00',
        outcome: { state: 'decided_without_reply', text: 'Decided without your reply: Set clock-out to 18:00.', reason: 'Worker unreachable; the gate log shows 18:00.' },
        questions: [{ asked_at: '2026-04-16T08:00:00', message: item.message, reminded_at: '2026-04-16T16:00:00', answer: null }],
      },
      {
        exception_id: 'P3-E001-2026-04-13', date: '2026-04-13', updated_at: '2026-04-16T10:00:00',
        outcome: { state: 'fixed', text: 'Fixed: Correct clock-out to 17:45.', reason: null },
        questions: [{
          asked_at: '2026-04-16T08:00:00', message: 'Did you leave at 18:00?', reminded_at: null,
          answer: { confirmed: false, text: 'I left at quarter to six.', time: '17:45', replied_at: '2026-04-16T09:00:00' },
        }],
      },
    ]
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [], notices: [] })
    vi.mocked(getWorkerHistory).mockResolvedValue(history)
    const user = userEvent.setup()
    render(<WorkerInbox />)
    await user.click(await screen.findByRole('button', { name: 'My history' }))
    const [first, second] = await screen.findAllByRole('article')
    expect(first).toHaveTextContent('Decided without your reply: Set clock-out to 18:00.')
    expect(first).toHaveTextContent('Reason: Worker unreachable; the gate log shows 18:00.')
    expect(first).toHaveTextContent('No answer yet.')
    expect(first).toHaveTextContent('Reminder sent')
    expect(second).toHaveTextContent('Fixed')
    expect(second).toHaveTextContent('You answered No — “I left at quarter to six.” (time: 17:45)')
  })

  it('shows a history load error and retries', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [], notices: [] })
    vi.mocked(getWorkerHistory).mockRejectedValueOnce(new Error('Your history could not be loaded.'))
    vi.mocked(getWorkerHistory).mockResolvedValueOnce([])
    const user = userEvent.setup()
    render(<WorkerInbox />)
    await user.click(await screen.findByRole('button', { name: 'My history' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your history could not be loaded.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('No history yet')).toBeVisible()
  })

  it('offers Check again on an empty inbox', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValueOnce({ items: [], notices: [] })
    vi.mocked(getWorkerInbox).mockResolvedValueOnce({ items: [item], notices: [] })
    const user = userEvent.setup()
    render(<WorkerInbox />)
    await user.click(await screen.findByRole('button', { name: 'Check again' }))
    expect(await screen.findByText(item.message)).toBeVisible()
  })

  it('says one more step when the answer still needs an exact time', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [item], notices: [] })
    vi.mocked(sendReply).mockResolvedValue({
      exception_id: item.exception_id, confirmed: false, needs_actual_time: true,
      time_review: { stage: 'manual', approximate: false },
    })
    const user = userEvent.setup()
    render(<WorkerInbox actor={{ id: 'E001', name: 'Amit Verma' }} />)
    await user.click(await screen.findByRole('button', { name: 'No' }))
    await user.type(screen.getByLabelText(item.reply_prompt), 'Stayed late, not sure when.')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByRole('heading', { name: /Thanks, Amit. One more step./ })).toHaveFocus()
    expect(screen.getByLabelText('Exact clock-out time')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'See my history' })).not.toBeInTheDocument()
  })

  it('has an Ask tab whose case source opens the case in My history', async () => {
    vi.mocked(getWorkerInbox).mockResolvedValue({ items: [], notices: [] })
    vi.mocked(getAskHistory).mockResolvedValue({
      items: [],
      limits: {
        max_chars: 300, questions_per_hour: 10, questions_left_this_hour: 10,
        retry_after_seconds: null, llm_configured: false, llm_calls_left_today: 60,
      },
    })
    vi.mocked(askQuestion).mockResolvedValue({
      question_id: 3, question: 'Why was my punch on Tuesday flagged?', kind: 'answer',
      source: 'template', label: 'Template answer', reason: 'llm_unavailable', refusal_code: null,
      answer: 'You have 1 attendance case on Tue 14 Apr 2026.',
      sources: [{ kind: 'case', id: item.exception_id, label: 'P1 · 2026-04-14', text: 'Clock-in 09:00', in_history: true }],
      intents: ['my_cases'], asked_at: '2026-04-16T08:00:00', llm_calls: 0, latency_ms: null,
      limits: {
        max_chars: 300, questions_per_hour: 10, questions_left_this_hour: 9,
        retry_after_seconds: null, llm_configured: false, llm_calls_left_today: 60,
      },
    })
    vi.mocked(getWorkerHistory).mockResolvedValue([{
      exception_id: item.exception_id, date: item.date, updated_at: '2026-04-16T08:00:00',
      outcome: { state: 'with_supervisor', text: 'Your supervisor is reviewing it.', reason: null },
      questions: [{ asked_at: '2026-04-16T08:00:00', message: item.message, reminded_at: null, answer: null }],
    }])
    const user = userEvent.setup()
    render(<WorkerInbox />)
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(screen.getByRole('button', { name: 'Ask' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(await screen.findByRole('button', { name: 'Why was my punch on Tuesday flagged?' }))
    await user.click(await screen.findByRole('button', { name: /P1 · 2026-04-14/ }))
    const card = await screen.findByRole('article', { name: /Case from/ })
    expect(card).toHaveClass('focused')
    expect(screen.getByRole('button', { name: 'My history' })).toHaveAttribute('aria-pressed', 'true')
  })
})
