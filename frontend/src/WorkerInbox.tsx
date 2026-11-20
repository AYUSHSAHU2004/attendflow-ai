import { useEffect, useRef, useState } from 'react'
import type { Actor } from './actors'
import {
  confirmWorkerTime,
  getWorkerHistory,
  getWorkerInbox,
  sendReply,
  submitManualTime,
  type WorkerHistoryItem,
  type WorkerMessage,
  type WorkerNotice,
  type WorkerReceipt,
} from './api'

// Phase 17: the worker's phone-first inbox. One question per card, big Yes/No buttons, a
// clear confirmation after each reply and a "My history" view. The worker identity comes
// from the page (main.tsx); the API only ever returns the caller's own cases.

export function displayDate(value: string) {
  return new Intl.DateTimeFormat('en-IN', {
    weekday: 'short',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(value + 'T00:00:00Z'))
}

function shortStamp(value: string) {
  const day = new Intl.DateTimeFormat('en-IN', {
    weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC',
  }).format(new Date(value.slice(0, 10) + 'T00:00:00Z'))
  return `${day}, ${value.slice(11, 16)}`
}

type Confirmation = { title: string; text: string; moreToDo?: boolean }

function QuestionCard({
  item,
  position,
  onResult,
}: {
  item: WorkerMessage
  position: string
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
  const titleId = `question-${item.exception_id}`

  async function submit(action: () => Promise<WorkerReceipt>) {
    setBusy(true)
    setError('')
    try {
      onResult(await action())
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Your reply could not be saved. Please try again.')
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
    <article className="question-card worker-card" aria-labelledby={titleId}>
      <div className="card-top">
        <time dateTime={item.date}>{displayDate(item.date)}</time>
        <span className="step">{position}</span>
      </div>
      {item.reminder && (
        <p className="reminder" role="note"><strong>Reminder:</strong> {item.reminder.text.replace(/^Reminder: /, '')}</p>
      )}
      {item.status_note && <p className="status-note">{item.status_note}</p>}
      <p className="question-text" id={titleId}>{item.message}</p>
      {item.needs_actual_time ? (
        review?.stage === 'candidate' && !editing ? (
          <section aria-label="Review your clock-out" className="answer-area">
            <p className="big-line">We understood you left at <strong>{review.timestamp?.slice(11, 16)}</strong>
              {review.timestamp?.slice(0, 10) !== item.date && review.timestamp
                ? ` on ${displayDate(review.timestamp.slice(0, 10))}` : ''}
              {review.approximate ? ' (approximately)' : ''}. Is that right?</p>
            {review.impact_note && <p>{review.impact_note}</p>}
            <div className="actions stack">
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
          <form className="answer-area" onSubmit={(event) => {
            event.preventDefault()
            void submit(() => submitManualTime(item.exception_id, {
              time: actualTime, actual_date: actualDate || undefined,
            }))
          }}>
            <label htmlFor={`time-${item.exception_id}`}>Exact clock-out time</label>
            <input id={`time-${item.exception_id}`} type="time" required value={actualTime}
              className="big-input" autoComplete="off" enterKeyHint="send"
              aria-describedby={`time-help-${item.exception_id}`}
              onChange={(event) => setActualTime(event.target.value)} disabled={busy} />
            <p className="hint" id={`time-help-${item.exception_id}`}>Use the 24-hour time, for example 18:30.</p>
            <label htmlFor={`date-${item.exception_id}`}>Clock-out date (if needed)</label>
            <input id={`date-${item.exception_id}`} type="date" value={actualDate} className="big-input"
              onChange={(event) => setActualDate(event.target.value)} disabled={busy} />
            <div className="actions stack">
              <button disabled={busy || !actualTime}>{busy ? 'Sending…' : 'Send time'}</button>
              {editing && <button className="secondary" type="button" disabled={busy}
                onClick={() => setEditing(false)}>Back</button>}
            </div>
          </form>
        ) : (
          <p className="message-status">Your details were saved. This question is still open.</p>
        )
      ) : showDetails ? (
        <form className="answer-area" onSubmit={(event) => { event.preventDefault(); void reply(false) }}>
          <label htmlFor={`details-${item.exception_id}`}>{item.reply_prompt}</label>
          <textarea
            id={`details-${item.exception_id}`}
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={busy}
            required
            maxLength={2000}
            rows={4}
            enterKeyHint="send"
            autoFocus
          />
          <p className="hint">For example: “I left at 19:30 because the truck was late.”</p>
          <div className="actions stack">
            <button type="submit" disabled={busy || !text.trim()}>{busy ? 'Sending…' : 'Send'}</button>
            <button className="secondary" type="button" disabled={busy} onClick={() => setShowDetails(false)}>
              Back
            </button>
          </div>
        </form>
      ) : (
        <div className="actions yes-no">
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

const OUTCOME_LABELS: Record<string, string> = {
  waiting_for_you: 'Waiting for you',
  with_supervisor: 'With your supervisor',
  with_payroll: 'With payroll',
  decided_without_reply: 'Decided without your reply',
  decided: 'Decided',
  fixed: 'Fixed',
  closed_no_change: 'Closed',
}

function HistoryCard({ item }: { item: WorkerHistoryItem }) {
  const state = item.outcome.state
  const done = ['fixed', 'decided', 'decided_without_reply', 'closed_no_change'].includes(state)
  return (
    <article className="question-card history-card" aria-label={`Case from ${displayDate(item.date)}`}>
      <div className="card-top">
        <time dateTime={item.date}>{displayDate(item.date)}</time>
        <span className={done ? 'state-tag done' : 'state-tag'}>
          <span aria-hidden="true">{done ? '✓ ' : '… '}</span>{OUTCOME_LABELS[state] ?? state}
        </span>
      </div>
      <p className="outcome">{item.outcome.text}</p>
      {item.outcome.reason && <p><strong>Reason:</strong> {item.outcome.reason}</p>}
      <ol className="timeline">
        {item.questions.map((question, index) => (
          <li key={index}>
            <p><span className="who">We asked</span> <span className="hint">{shortStamp(question.asked_at)}</span></p>
            <p>{question.message}</p>
            {question.reminded_at && <p className="hint">Reminder sent {shortStamp(question.reminded_at)}</p>}
            {question.answer ? (
              <p>
                <span className="who">You answered</span>{' '}
                {question.answer.confirmed === true ? 'Yes' : question.answer.confirmed === false ? 'No' : ''}
                {question.answer.text ? ` — “${question.answer.text}”` : ''}
                {question.answer.time ? ` (time: ${question.answer.time})` : ''}
              </p>
            ) : (
              <p className="hint">No answer yet.</p>
            )}
          </li>
        ))}
      </ol>
    </article>
  )
}

function firstName(actor?: Actor) {
  return actor?.name.split(' ')[0] ?? ''
}

export function WorkerInbox({ actor }: { actor?: Actor } = {}) {
  const [view, setView] = useState<'questions' | 'history'>('questions')
  const [items, setItems] = useState<WorkerMessage[] | null>(null)
  const [notices, setNotices] = useState<WorkerNotice[]>([])
  const [history, setHistory] = useState<WorkerHistoryItem[] | null>(null)
  const [error, setError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const [request, setRequest] = useState(0)
  const confirmRef = useRef<HTMLHeadingElement>(null)
  const name = firstName(actor)

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

  useEffect(() => {
    if (view !== 'history') return
    const controller = new AbortController()
    setHistory(null)
    setHistoryError('')
    getWorkerHistory(controller.signal)
      .then((list) => { if (!controller.signal.aborted) setHistory(list) })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) {
          setHistoryError(failure instanceof Error ? failure.message : 'Your history could not be loaded.')
        }
      })
    return () => controller.abort()
  }, [view, request])

  useEffect(() => {
    if (confirmation) confirmRef.current?.focus()
  }, [confirmation])

  function reload() {
    setError('')
    setItems(null)
    setRequest(request + 1)
  }

  function onResult(result: WorkerReceipt) {
    setItems((current) => current?.flatMap((question) => {
      if (question.exception_id !== result.exception_id) return [question]
      return result.needs_actual_time
        ? [{ ...question, needs_actual_time: true, time_review: result.time_review }] : []
    }) ?? [])
    const thanks = name ? `Thanks, ${name}.` : 'Thanks.'
    if (result.time_review?.stage === 'confirmed') {
      const time = result.time_review.timestamp?.slice(11, 16)
      setConfirmation({
        title: `${thanks} Your time is saved.`,
        text: `${time} sent to your supervisor. ${result.time_review.impact_note ?? ''}`.trim(),
      })
    } else if (result.needs_actual_time && result.time_review?.stage === 'manual') {
      setConfirmation({
        title: `${thanks} One more step.`,
        text: 'We could not read one exact time from your answer. Please enter the time below.',
        moreToDo: true,
      })
    } else if (result.needs_actual_time && result.time_review?.stage === 'candidate') {
      setConfirmation({
        title: `${thanks} One more step.`,
        text: 'Please check the time we understood, below.',
        moreToDo: true,
      })
    } else if (result.confirmed) {
      setConfirmation({
        title: `${thanks} Your answer is saved.`,
        text: 'Confirmation sent. Your supervisor will review it.',
      })
    } else {
      setConfirmation({ title: `${thanks} Your answer is saved.`, text: 'Thanks. Your response was saved.' })
    }
  }

  const open = items?.length ?? 0
  return (
    <main className="page worker-inbox" id="main">
      <h1>{name ? `Hi ${name}` : 'Attendance inbox'}</h1>
      <p className="lede">Your attendance questions. Answer when you can; it takes a minute.</p>
      <nav className="view-switch" aria-label="Inbox views">
        <button type="button" className={view === 'questions' ? 'active' : ''} aria-pressed={view === 'questions'}
          onClick={() => setView('questions')}>
          Questions{items !== null && open > 0 ? ` (${open})` : ''}
        </button>
        <button type="button" className={view === 'history' ? 'active' : ''} aria-pressed={view === 'history'}
          onClick={() => setView('history')}>
          My history
        </button>
      </nav>

      {confirmation && (
        <section className="question-card confirm-card" aria-labelledby="confirm-title">
          <h2 id="confirm-title" ref={confirmRef} tabIndex={-1}>
            <span aria-hidden="true">✓ </span>{confirmation.title}
          </h2>
          <p role="status">{confirmation.text}</p>
          {!confirmation.moreToDo && <p className="hint">You can follow it under My history.</p>}
          <div className="actions stack">
            <button type="button" onClick={() => setConfirmation(null)}>{confirmation.moreToDo ? 'OK' : 'Done'}</button>
            {!confirmation.moreToDo && (
              <button type="button" className="secondary" onClick={() => { setConfirmation(null); setView('history') }}>
                See my history
              </button>
            )}
          </div>
        </section>
      )}

      {view === 'questions' ? (
        <section aria-label="Questions">
          {error ? (
            <div className="question-card">
              <p role="alert" className="error">{error}</p>
              <button onClick={reload}>Try again</button>
            </div>
          ) : items === null ? (
            <p role="status" className="panel">Loading your questions…</p>
          ) : items.length === 0 ? (
            <div className="panel empty-state">
              <p className="big-line">{notices.length ? 'No open questions' : 'Nothing needs your attention'}</p>
              <p className="hint">We will ask here if a record needs your answer.</p>
              <button type="button" className="secondary" onClick={reload}>Check again</button>
            </div>
          ) : items.map((item, index) => (
            <QuestionCard key={item.exception_id} item={item}
              position={`Question ${index + 1} of ${items.length}`} onResult={onResult} />
          ))}
          {items !== null && !error && notices.length > 0 && (
            <section aria-label="Updates">
              {notices.map((notice) => <NoticeCard key={notice.exception_id + notice.kind} notice={notice} />)}
            </section>
          )}
        </section>
      ) : (
        <section aria-label="My history">
          {historyError ? (
            <div className="question-card">
              <p role="alert" className="error">{historyError}</p>
              <button onClick={() => setRequest(request + 1)}>Try again</button>
            </div>
          ) : history === null ? (
            <p role="status" className="panel">Loading your history…</p>
          ) : history.length === 0 ? (
            <div className="panel empty-state">
              <p className="big-line">No history yet</p>
              <p className="hint">Questions you answer, and what happened next, show up here.</p>
            </div>
          ) : history.map((item) => <HistoryCard key={item.exception_id} item={item} />)}
        </section>
      )}
    </main>
  )
}
