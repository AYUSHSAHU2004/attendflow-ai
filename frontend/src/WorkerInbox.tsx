import { useEffect, useState } from 'react'
import {
  confirmWorkerTime,
  getWorkerInbox,
  sendReply,
  submitManualTime,
  type WorkerMessage,
  type WorkerNotice,
  type WorkerReceipt,
} from './api'

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
  onResult,
}: {
  item: WorkerMessage
  onResult: (result: WorkerReceipt) => void
}) {
  const [showDetails, setShowDetails] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const review = item.time_review
  const [actualTime, setActualTime] = useState(review?.timestamp?.slice(11, 16) ?? '')
  const [actualDate, setActualDate] = useState('')


  async function submit(action: () => Promise<WorkerReceipt>) {
    setBusy(true)
    setError('')
    try {
      onResult(await action())
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Your reply could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  function reply(confirmed: boolean) {
    return submit(() => sendReply(item.exception_id, {
      confirmed,
      text: confirmed ? undefined : text.trim(),
    }))
  }

  return (
    <article className="question-card">
      <time dateTime={item.date}>{displayDate(item.date)}</time>
      {item.reminder && (
        <p className="reminder" role="note"><strong>Reminder:</strong> {item.reminder.text.replace(/^Reminder: /, '')}</p>
      )}
      {item.status_note && <p className="status-note">{item.status_note}</p>}
      <p className="question-text">{item.message}</p>
      {item.needs_actual_time ? (
        review?.stage === 'candidate' && !editing ? (
          <section aria-label="Review your clock-out">
            <p>We understood you left at {review.timestamp?.slice(11, 16)}
              {review.timestamp?.slice(0, 10) !== item.date && review.timestamp
                ? ` on ${displayDate(review.timestamp.slice(0, 10))}` : ''}
              {review.approximate ? ' (approximately)' : ''}. Is that right?</p>
            {review.impact_note && <p>{review.impact_note}</p>}
            <div className="actions">
              <button disabled={busy} onClick={() => void submit(() => confirmWorkerTime(item.exception_id))}>
                {busy ? 'Confirming…' : 'Confirm'}
              </button>
              <button className="secondary" disabled={busy} onClick={() => {
                setActualTime(review.timestamp?.slice(11, 16) ?? '')
                setActualDate(review.timestamp?.slice(0, 10) ?? '')
                setEditing(true)
              }}>Edit</button>
            </div>
          </section>
        ) : review?.stage === 'manual' || editing ? (
          <form onSubmit={(event) => {
            event.preventDefault()
            void submit(() => submitManualTime(item.exception_id, {
              time: actualTime, actual_date: actualDate || undefined,
            }))
          }}>
            <label htmlFor={`time-${item.exception_id}`}>Exact clock-out time</label>
            <input id={`time-${item.exception_id}`} type="time" required value={actualTime}
              onChange={(event) => setActualTime(event.target.value)} disabled={busy} />
            <label htmlFor={`date-${item.exception_id}`}>Clock-out date (if needed)</label>
            <input id={`date-${item.exception_id}`} type="date" value={actualDate}
              onChange={(event) => setActualDate(event.target.value)} disabled={busy} />
            <div className="actions">
              <button disabled={busy || !actualTime}>{busy ? 'Sending…' : 'Send time'}</button>
              {editing && <button className="secondary" type="button" disabled={busy}
                onClick={() => setEditing(false)}>Back</button>}
            </div>
          </form>
        ) : (
          <p className="message-status">Your details were saved. This question is still open.</p>
        )
      ) : showDetails ? (
        <form onSubmit={(event) => { event.preventDefault(); void reply(false) }}>
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
          <button disabled={busy} onClick={() => void reply(true)}>{busy ? 'Sending…' : 'Yes'}</button>
          <button className="secondary" disabled={busy} onClick={() => setShowDetails(true)}>No</button>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </article>
  )
}

// Phase 13: cases the worker can no longer answer (decided without them, or with payroll).
function NoticeCard({ notice }: { notice: WorkerNotice }) {
  return (
    <article className="question-card notice-card" aria-label={notice.title}>
      <time dateTime={notice.date}>{displayDate(notice.date)}</time>
      <h2>{notice.title}</h2>
      <p>{notice.text}</p>
      {notice.reason && <p><strong>Reason:</strong> {notice.reason}</p>}
    </article>
  )
}

export function WorkerInbox() {
  const [items, setItems] = useState<WorkerMessage[] | null>(null)
  const [notices, setNotices] = useState<WorkerNotice[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [request, setRequest] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getWorkerInbox(controller.signal)
      .then((inbox) => {
        if (!controller.signal.aborted) {
          setItems(inbox.items)
          setNotices(inbox.notices)
        }
      })
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
        <p className="panel">{notices.length ? 'No open questions' : 'Nothing needs your attention'}</p>
      ) : items.map((item) => (
        <QuestionCard key={item.exception_id} item={item} onResult={(result) => {
          setItems((current) => current?.flatMap((question) => {
            if (question.exception_id !== result.exception_id) return [question]
            return result.needs_actual_time
              ? [{ ...question, needs_actual_time: true, time_review: result.time_review }] : []
          }) ?? [])
          if (result.time_review?.stage === 'confirmed') {
            const time = result.time_review.timestamp?.slice(11, 16)
            setNotice(`${time} sent to your supervisor. ${result.time_review.impact_note ?? ''}`.trim())
          } else {
            setNotice(result.confirmed
              ? 'Confirmation sent. Your supervisor will review it.'
              : 'Thanks. Your response was saved.')
          }
        }} />
      ))}
      {items !== null && !error && notices.length > 0 && (
        <section aria-label="Updates">
          {notices.map((notice) => <NoticeCard key={notice.exception_id + notice.kind} notice={notice} />)}
        </section>
      )}
    </main>
  )
}
