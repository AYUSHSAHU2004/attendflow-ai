import { useState, type FormEvent } from 'react'
import type { EmployeeIdentity } from './actors'
import { ApiError, login, logout } from './api'

type Role = EmployeeIdentity['role']

export const roleHome: Record<Role, string> = {
  worker: '/',
  supervisor: '/supervisor',
  payroll_admin: '/dashboard',
}

export const roleLabel: Record<Role, string> = {
  worker: 'Worker',
  supervisor: 'Supervisor',
  payroll_admin: 'Payroll admin',
}

const pages: Record<Role, string[]> = {
  worker: ['/'],
  supervisor: ['/supervisor', '/supervisor/dashboard', '/supervisor/payroll', '/activity'],
  payroll_admin: ['/dashboard', '/admin', '/payroll', '/activity'],
}

export function sessionDestination(role: Role, path: string): string {
  return pages[role].includes(path) ? path : roleHome[role]
}

const demoPeople = [
  ['Amit', 'amit@demo.attendflow.test'],
  ['Ravi', 'ravi@demo.attendflow.test'],
  ['Priya', 'priya@demo.attendflow.test'],
]

export function LoginPage({ guided, onLogin }: {
  guided: boolean
  onLogin: (employee: EmployeeIdentity) => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError('')
    try {
      const result = await login(email, password)
      if (!result.employee) throw new Error('Login returned no employee')
      onLogin(result.employee)
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : 'Sign-in is unavailable. Try again.')
    } finally {
      setPassword('')
      setPending(false)
    }
  }

  return <main className="page login-page" id="main">
    <h1>Sign in to AttendFlow</h1>
    <form className="question-card login-form" onSubmit={submit}>
      <label htmlFor="login-email">Email</label>
      <input id="login-email" type="email" autoComplete="username" required maxLength={254}
        value={email} onChange={event => setEmail(event.target.value)} disabled={pending} />
      <label htmlFor="login-password">Password</label>
      <input id="login-password" type="password" autoComplete="current-password" required
        maxLength={1024} value={password} onChange={event => setPassword(event.target.value)}
        disabled={pending} />
      {error && <p className="error" role="alert">{error}</p>}
      <button disabled={pending}>{pending ? 'Signing in…' : 'Sign in'}</button>
    </form>
    {guided && <section aria-labelledby="demo-accounts-title" className="question-card">
      <h2 id="demo-accounts-title">Demo accounts</h2>
      <div className="actions">
        {demoPeople.map(([name, address]) => (
          <button key={address} type="button" className="secondary" disabled={pending}
            onClick={() => setEmail(address)}>{name}</button>
        ))}
      </div>
    </section>}
  </main>
}

export function SessionBadge({ employee, onLogout }: {
  employee: EmployeeIdentity
  onLogout: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  async function signOut() {
    setBusy(true)
    setFailed(false)
    try {
      await logout()
      onLogout()
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  return <div className="session-badge">
    <span className="identity">{employee.name} · {roleLabel[employee.role]}</span>
    <button type="button" className="secondary small" disabled={busy}
      onClick={() => void signOut()}>{busy ? 'Signing out…' : 'Logout'}</button>
    {failed && <span role="alert">Sign-out failed. Try again.</span>}
  </div>
}
