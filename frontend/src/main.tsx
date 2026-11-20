import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ActivityPage } from './ActivityPage'
import { AdminPage } from './AdminPage'
import { ApiError, getAuthState } from './api'
import { LoginPage, roleHome, SessionBadge, sessionDestination } from './Auth'
import {
  activityActor, adminActor, dashboardActor, payrollActor, supervisorActor,
  supervisorDashboardPath, supervisorPayrollPath, workerActor, enableSessionAuth,
  setSessionEmployee, type EmployeeIdentity,
} from './actors'
import { DashboardPage } from './DashboardPage'
import { DevPage } from './DevPage'
import { PayrollPage } from './PayrollPage'
import { SupervisorPage } from './SupervisorPage'
import { WorkerInbox } from './WorkerInbox'
import './styles.css'

const root = createRoot(document.getElementById('root')!)

function renderLogin(guided: boolean) {
  document.title = 'AttendFlow | Sign in'
  root.render(<StrictMode>
    <LoginPage guided={guided} onLogin={employee => window.location.replace(roleHome[employee.role])} />
  </StrictMode>)
}

async function start() {
  try {
    const auth = await getAuthState()
    if (auth.mode === 'session' && auth.employee) {
      enableSessionAuth()
      setSessionEmployee(auth.employee)
      const path = window.location.pathname
      const destination = sessionDestination(auth.employee.role, path)
      const query = new URL(window.location.href).searchParams
      if (path !== destination || query.has('as')) {
        if (path !== destination) {
          window.location.replace(destination)
          return
        }
        query.delete('as')
        window.location.replace(destination + (query.size ? '?' + query.toString() : ''))
        return
      }
      renderPage(auth.employee)
    } else {
      renderPage()
    }
  } catch (failure) {
    if (failure instanceof ApiError && failure.status === 401 && failure.code === 'login_required') {
      enableSessionAuth()
      const details = failure.details as { demo_accounts?: boolean } | null
      if (window.location.pathname !== '/login') window.location.replace('/login')
      else renderLogin(details?.demo_accounts === true)
      return
    }
    root.render(<main className="page" id="main">
      <h1>AttendFlow is unavailable</h1>
      <button onClick={() => window.location.reload()}>Try again</button>
    </main>)
  }
}

function renderPage(employee?: EmployeeIdentity) {
  const path = window.location.pathname
  const page = path === '/dev' ? 'dev'
    : path === '/supervisor' ? 'supervisor'
      : path === '/admin' ? 'admin'
        : path === '/activity' ? 'activity'
          : path === '/dashboard' || path === supervisorDashboardPath ? 'dashboard'
            : path === '/payroll' || path === supervisorPayrollPath ? 'payroll'
              : 'worker'
  const actor = page === 'worker' ? workerActor
    : page === 'admin' ? adminActor
      : page === 'activity' ? activityActor
        : page === 'dashboard' ? dashboardActor
          : page === 'payroll' ? payrollActor
            : supervisorActor
  document.title = {
    activity: 'AttendFlow | Activity',
    admin: 'AttendFlow | All exceptions',
    dashboard: 'AttendFlow | Operations dashboard',
    dev: 'AttendFlow | Dev tools',
    payroll: 'AttendFlow | Payroll readiness',
    supervisor: 'AttendFlow | Decisions',
    worker: 'AttendFlow | Attendance inbox',
  }[page]

  root.render(
    <StrictMode>
      <header className={page === 'dashboard' ? 'site-header dashboard-header' : 'site-header'}>
        <a href={employee ? roleHome[employee.role] : '/'} className="brand">
          <span className="brand-mark" aria-hidden="true">A</span>
          AttendFlow
        </a>
        {employee
          ? <SessionBadge employee={employee} onLogout={() => window.location.replace('/login')} />
          : <span className="identity">{actor.name}</span>}
      </header>
      {page === 'dev' ? <DevPage />
        : page === 'supervisor' ? <SupervisorPage />
          : page === 'admin' ? <AdminPage />
            : page === 'activity' ? <ActivityPage />
              : page === 'dashboard' ? <DashboardPage />
                : page === 'payroll' ? <PayrollPage />
                  : <WorkerInbox actor={workerActor} />}
    </StrictMode>,
  )
}

void start()
