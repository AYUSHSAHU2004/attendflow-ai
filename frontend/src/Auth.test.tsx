import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { EmployeeIdentity } from './actors'
import { LoginPage, SessionBadge, sessionDestination } from './Auth'

const worker: EmployeeIdentity = { id: 'E001', name: 'Amit Verma', role: 'worker' }
const fetchMock = vi.fn<typeof fetch>()

function reply(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status })
}

describe('employee login', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => vi.unstubAllGlobals())

  it('fills only the email for a Guided demo account and signs the employee in', async () => {
    fetchMock.mockResolvedValue(reply(200, { mode: 'session', employee: worker, demo_accounts: true }))
    const user = userEvent.setup()
    const onLogin = vi.fn()
    render(<LoginPage guided onLogin={onLogin} />)
    await user.click(screen.getByRole('button', { name: 'Amit' }))
    expect(screen.getByLabelText('Email')).toHaveValue('amit@demo.attendflow.test')
    expect(screen.getByLabelText('Password')).toHaveValue('')
    await user.type(screen.getByLabelText('Password'), 'example test passphrase')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(onLogin).toHaveBeenCalledExactlyOnceWith(worker)
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/auth\/login$/)
    const request = fetchMock.mock.calls[0][1]!
    expect(request.credentials).toBe('same-origin')
    expect(new Headers(request.headers).has('X-Actor-Id')).toBe(false)
    expect(JSON.parse(String(request.body))).toEqual({
      email: 'amit@demo.attendflow.test', password: 'example test passphrase',
    })
  })

  it('hides demo identities in Locked mode and shows a generic credential error', async () => {
    fetchMock.mockResolvedValue(reply(401, {
      error: { code: 'invalid_credentials', message: 'Invalid email or password' },
    }))
    const user = userEvent.setup()
    const onLogin = vi.fn()
    render(<LoginPage guided={false} onLogin={onLogin} />)
    expect(screen.queryByText('Demo accounts')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Email'), 'employee@example.test')
    await user.type(screen.getByLabelText('Password'), 'wrong password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
    expect(screen.getByLabelText('Password')).toHaveValue('')
    expect(onLogin).not.toHaveBeenCalled()
  })

  it('shows name and role and signs out via the API', async () => {
    fetchMock.mockResolvedValue(reply(200, { ok: true }))
    const user = userEvent.setup()
    const onLogout = vi.fn()
    render(<SessionBadge employee={worker} onLogout={onLogout} />)
    expect(screen.getByText('Amit Verma · Worker')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Logout' }))
    expect(onLogout).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/auth\/logout$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
  })
})

it.each([
  ['worker', '/dashboard', '/'],
  ['worker', '/', '/'],
  ['supervisor', '/admin', '/supervisor'],
  ['supervisor', '/supervisor/payroll', '/supervisor/payroll'],
  ['payroll_admin', '/login', '/dashboard'],
  ['payroll_admin', '/activity', '/activity'],
  ['payroll_admin', '/dev', '/dashboard'],
] as const)('routes %s from %s to %s', (role, path, destination) => {
  expect(sessionDestination(role, path)).toBe(destination)
})
