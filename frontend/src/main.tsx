import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { supervisorActor, workerActor } from './actors'
import { DevPage } from './DevPage'
import { WorkerInbox } from './WorkerInbox'
import './styles.css'

const dev = window.location.pathname === '/dev'
const actor = dev ? supervisorActor : workerActor

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <header className="site-header">
      <a href="/" className="brand">
        <span className="brand-mark" aria-hidden="true">A</span>
        AttendFlow
      </a>
      <span className="identity">{actor.name}</span>
    </header>
    {dev ? <DevPage /> : <WorkerInbox />}
  </StrictMode>,
)
