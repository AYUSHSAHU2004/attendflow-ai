import { useEffect, useState } from 'react'
import { getWorkerMessages, sendReply, type WorkerMessage } from './api'

export function displayDate(value: string) {
  return new Intl.DateTimeFormat('en-IN', {
    weekday: 'short',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(value + 'T00:00:00Z'))
}

function QuestionCard({
  item,
  onReply,
}: {
  item: WorkerMessage
  onReply: (confirmed: boolean, text?: string) => Promise<void>
}) {
  const [showDetails, setShowDetails] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(confirmed: boolean) {
    setBusy(true)
    setError('')
    try {
      await onReply(confirmed, confirmed ? undefined : text.trim())
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Your reply could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="question-card">
      <time dateTime={item.date}>{displayDate(item.date)}</time>
      <p className="question-text">{item.message}</p>
      {item.needs_actual_time ? (
        <p className="message-status">Your details were saved. This question is still open.</p>
      ) : showDetails ? (
        <form onSubmit={(event) => { event.preventDefault(); void submit(false) }}>
          <label htmlFor={`details-${item.exception_id}`}>{item.reply_prompt}</label>
          <textarea
            id={`details-${item.exception_id}`}
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={busy}
            required
            maxLength={2000}
            rows={4}
          />
          <div className="actions">
            <button type="submit" disabled={busy || !text.trim()}>{busy ? 'Sending…' : 'Send'}</button>
            <button className="secondary" type="button" disabled={busy} onClick={() => setShowDetails(false)}>
              Back
            </button>
          </div>
        </form>
      ) : (
        <div className="actions">
          <button disabled={busy} onClick={() => void submit(true)}>{busy ? 'Sending…' : 'Yes'}</button>
          <button className="secondary" disabled={busy} onClick={() => setShowDetails(true)}>No</button>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </article>
  )
}

export function WorkerInbox() {
  const [items, setItems] = useState<WorkerMessage[] | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [request, setRequest] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getWorkerMessages(controller.signal)
      .then((messages) => { if (!controller.signal.aborted) setItems(messages) })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) {
          setError(failure instanceof Error ? failure.message : 'The inbox could not be loaded.')
        }
      })
    return () => controller.abort()
  }, [request])

  return (
    <main className="page" id="main">
      <h1>Attendance inbox</h1>
      {notice && <p role="status" className="notice">{notice}</p>}
      {error ? (
        <section className="question-card">
          <p role="alert" className="error">{error}</p>
          <button onClick={() => { setError(''); setRequest(request + 1) }}>Try again</button>
        </section>
      ) : items === null ? (
        <p role="status" className="panel">Loading your questions…</p>
      ) : items.length === 0 ? (
        <p className="panel">Nothing needs your attention</p>
      ) : items.map((item) => (
        <QuestionCard key={item.exception_id} item={item} onReply={async (confirmed, text) => {
          const result = await sendReply(item.exception_id, { confirmed, text })
          setItems((current) => current?.flatMap((question) => {
            if (question.exception_id !== result.exception_id) return [question]
            return result.needs_actual_time ? [{ ...question, needs_actual_time: true }] : []
          }) ?? [])
          setNotice(result.confirmed
            ? 'Confirmation sent. Your supervisor will review it.'
            : 'Thanks. Your response was saved.')
        }} />
      ))}
    </main>
  )
}
