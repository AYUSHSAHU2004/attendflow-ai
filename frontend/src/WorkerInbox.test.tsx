import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { confirmWorkerTime, getWorkerInbox, sendReply, submitManualTime, type WorkerMessage } from './api'
import { WorkerInbox } from './WorkerInbox'

vi.mock('./api', () => ({
  getWorkerInbox: vi.fn(),
  sendReply: vi.fn(),
  confirmWorkerTime: vi.fn(),
  submitManualTime: vi.fn(),
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
    expect(await screen.findByText(/We understood you left at 19:30/)).toBeVisible()
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
})
