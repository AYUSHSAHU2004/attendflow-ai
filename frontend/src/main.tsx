import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { supervisorActor, workerActor } from './actors'
import { DevPage } from './DevPage'
import { SupervisorPage } from './SupervisorPage'
import { WorkerInbox } from './WorkerInbox'
import './styles.css'

const path = window.location.pathname
const page = path === '/dev' ? 'dev' : path === '/supervisor' ? 'supervisor' : 'worker'
const actor = page === 'worker' ? workerActor : supervisorActor
document.title = {
  dev: 'AttendFlow | Dev tools',
  supervisor: 'AttendFlow | Decisions',
  worker: 'AttendFlow | Attendance inbox',
}[page]

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <header className="site-header">
      <a href="/" className="brand">
        <span className="brand-mark" aria-hidden="true">A</span>
        AttendFlow
      </a>
      <span className="identity">{actor.name}</span>
    </header>
    {page === 'dev' ? <DevPage /> : page === 'supervisor' ? <SupervisorPage /> : <WorkerInbox />}
  </StrictMode>,
)
