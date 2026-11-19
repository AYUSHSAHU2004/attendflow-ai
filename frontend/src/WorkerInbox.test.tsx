import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getWorkerMessages, sendReply, type WorkerMessage } from './api'
import { WorkerInbox } from './WorkerInbox'

vi.mock('./api', () => ({
  getWorkerMessages: vi.fn(),
  sendReply: vi.fn(),
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
    vi.mocked(getWorkerMessages).mockResolvedValue([item])
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
    vi.mocked(getWorkerMessages).mockResolvedValue([item])
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
    vi.mocked(getWorkerMessages).mockResolvedValue([])
    render(<WorkerInbox />)
    expect(await screen.findByText('Nothing needs your attention')).toBeVisible()
  })

  it('shows a load error and retries the inbox request', async () => {
    vi.mocked(getWorkerMessages).mockRejectedValueOnce(new Error('The inbox could not be loaded.'))
    vi.mocked(getWorkerMessages).mockResolvedValueOnce([])
    const user = userEvent.setup()
    render(<WorkerInbox />)
    expect(await screen.findByRole('alert')).toHaveTextContent('The inbox could not be loaded.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Nothing needs your attention')).toBeVisible()
  })
})
