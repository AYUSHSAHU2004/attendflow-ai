import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ActivityPage } from './ActivityPage'
import { AdminPage } from './AdminPage'
import {
  activityActor, adminActor, dashboardActor, supervisorActor, supervisorDashboardPath, workerActor,
} from './actors'
import { DashboardPage } from './DashboardPage'
import { DevPage } from './DevPage'
import { SupervisorPage } from './SupervisorPage'
import { WorkerInbox } from './WorkerInbox'
import './styles.css'

const path = window.location.pathname
const page = path === '/dev' ? 'dev'
  : path === '/supervisor' ? 'supervisor'
    : path === '/admin' ? 'admin'
      : path === '/activity' ? 'activity'
        : path === '/dashboard' || path === supervisorDashboardPath ? 'dashboard'
          : 'worker'
const actor = page === 'worker' ? workerActor
  : page === 'admin' ? adminActor
    : page === 'activity' ? activityActor
      : page === 'dashboard' ? dashboardActor
        : supervisorActor
document.title = {
  activity: 'AttendFlow | Activity',
  admin: 'AttendFlow | All exceptions',
  dashboard: 'AttendFlow | Operations dashboard',
  dev: 'AttendFlow | Dev tools',
  supervisor: 'AttendFlow | Decisions',
  worker: 'AttendFlow | Attendance inbox',
}[page]

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <header className={page === 'dashboard' ? 'site-header dashboard-header' : 'site-header'}>
      <a href="/" className="brand">
        <span className="brand-mark" aria-hidden="true">A</span>
        AttendFlow
      </a>
      <span className="identity">{actor.name}</span>
    </header>
    {page === 'dev' ? <DevPage />
      : page === 'supervisor' ? <SupervisorPage />
        : page === 'admin' ? <AdminPage />
          : page === 'activity' ? <ActivityPage />
            : page === 'dashboard' ? <DashboardPage />
              : <WorkerInbox />}
  </StrictMode>,
)
