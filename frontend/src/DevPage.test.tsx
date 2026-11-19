import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import {
  askWorker, getInvestigation, pollInvestigation, startInvestigation,
  type InvestigationCase, type InvestigationJob,
} from './api'
import { DevPage } from './DevPage'

vi.mock('./api', () => ({
  askWorker: vi.fn(),
  getInvestigation: vi.fn(),
  pollInvestigation: vi.fn(),
  startInvestigation: vi.fn(),
}))

it('polls the job before enabling the worker handoff', async () => {
  const exception = 'P1-E001-2026-04-14'
  const location = `/api/exceptions/${exception}/investigate/job`
  const job = {
    id: 'job',
    exception_id: exception,
    started_at: '2026-04-15T00:00:00Z',
    deadline_at: '2026-04-15T00:00:45Z',
    finished_at: null,
    duration_ms: null,
    reason: null,
  } satisfies Partial<InvestigationJob>
  const investigation = {
    what_happened: 'The clock-out is missing.',
    who_to_ask: 'worker',
    next_action: 'Ask the worker to confirm the time.',
    fallback: true,
  } as InvestigationCase

  vi.mocked(startInvestigation).mockResolvedValue(location)
  vi.mocked(pollInvestigation)
    .mockResolvedValueOnce({ ...job, status: 'running' })
    .mockResolvedValueOnce({ ...job, status: 'completed' })
  vi.mocked(getInvestigation).mockResolvedValue(investigation)
  vi.mocked(askWorker).mockResolvedValue(undefined)

  const user = userEvent.setup()
  render(<DevPage />)
  expect(screen.getByRole('button', { name: 'Ask worker' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Investigate' }))
  expect(await screen.findByText('Waiting for the investigation…')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Ask worker' })).toBeDisabled()
  expect(await screen.findByText('Investigation ready.', {}, { timeout: 2000 })).toBeVisible()
  expect(pollInvestigation).toHaveBeenCalledTimes(2)
  expect(pollInvestigation).toHaveBeenLastCalledWith(location, expect.any(AbortSignal))
  await user.click(screen.getByRole('button', { name: 'Ask worker' }))
  expect(askWorker).toHaveBeenCalledWith(exception, expect.any(AbortSignal))
  expect(await screen.findByText(/Question sent/)).toBeVisible()
})
