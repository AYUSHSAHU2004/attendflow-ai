import { useEffect, useRef, useState } from 'react'
import {
  askWorker,
  getInvestigation,
  pollInvestigation,
  startInvestigation,
  type InvestigationCase,
} from './api'

function pause(signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }
    function finish() {
      clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      resolve()
    }
    const timer = setTimeout(finish, 750)
    signal.addEventListener('abort', finish, { once: true })
  })
}

export function DevPage() {
  const [id, setId] = useState('P1-E001-2026-04-14')
  const [investigation, setInvestigation] = useState<InvestigationCase | null>(null)
  const [busy, setBusy] = useState<'investigate' | 'ask' | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])

  async function act(action: 'investigate' | 'ask') {
    const current = new AbortController()
    controller.current = current
    setError('')
    setNotice('')
    setBusy(action)
    const exceptionId = id.trim()
    try {
      if (action === 'investigate') {
        setInvestigation(null)
        const location = await startInvestigation(exceptionId, current.signal)
        let job = await pollInvestigation(location, current.signal)
        while (job.status === 'running' && !current.signal.aborted) {
          await pause(current.signal)
          if (current.signal.aborted) return
          job = await pollInvestigation(location, current.signal)
        }
        setInvestigation(await getInvestigation(exceptionId, current.signal))
        setNotice(job.status === 'failed' ? 'The job stopped. The template case is ready.' : 'Investigation ready.')
      } else {
        await askWorker(exceptionId, current.signal)
        setInvestigation(null)
        setNotice('Question sent. Open the worker inbox to answer it.')
      }
    } catch (failure) {
      if (!current.signal.aborted) {
        setError(failure instanceof Error ? failure.message : 'The request failed.')
      }
    } finally {
      if (!current.signal.aborted) setBusy(null)
    }
  }

  return (
    <main className="page" id="main">
      <a className="text-link" href="/">Worker inbox</a>
      <h1>Investigate a case</h1>
      <form className="question-card" onSubmit={(event) => { event.preventDefault(); void act('investigate') }}>
        <label htmlFor="exception-id">Exception ID</label>
        <input
          id="exception-id"
          value={id}
          onChange={(event) => { setId(event.target.value); setInvestigation(null); setNotice(''); setError('') }}
          disabled={busy !== null}
          required
        />
        <div className="actions">
          <button disabled={busy !== null || !id.trim()}>
            {busy === 'investigate' ? 'Investigating…' : 'Investigate'}
          </button>
          <button type="button" className="secondary" onClick={() => void act('ask')}
            disabled={busy !== null || investigation?.who_to_ask !== 'worker'}>
            {busy === 'ask' ? 'Sending…' : 'Ask worker'}
          </button>
        </div>
      </form>
      {busy && <p role="status">{busy === 'investigate' ? 'Waiting for the investigation…' : 'Preparing the question…'}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {investigation && (
        <section className="question-card" aria-label="Investigation result">
          <p>{investigation.what_happened}</p>
          <p>{investigation.next_action}</p>
          <p className="message-status">{investigation.fallback ? 'Template investigation' : 'Validated investigation'}</p>
        </section>
      )}
    </main>
  )
}
