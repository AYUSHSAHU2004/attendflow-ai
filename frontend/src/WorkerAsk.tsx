import { useEffect, useRef, useState } from 'react'
import { askQuestion, getAskHistory, type AskAnswer, type AskLimits, type AskSource } from './api'

// Phase 20: the "Ask" tab of the worker inbox. The worker asks a short question about
// their own attendance or the policy. The server picks the facts (only this worker's),
// checks every number, date, ID and name in the answer, and falls back to a template or a
// plain "I can't answer that". Opening the tab reads the history only; it never calls the LLM.

export const SUGGESTIONS = [
  'How many sick days do I have left?',
  'Why was my punch on Tuesday flagged?',
  'What is my schedule this week?',
  'What happens if I forget to clock out?',
  'What is the late-arrival rule?',
]

const DEFAULT_MAX = 300

function errorText(failure: unknown): string {
  const problem = failure as { code?: string; message?: string; details?: { retry_after_seconds?: number } }
  if (problem?.code === 'qa_rate_limited') {
    const minutes = Math.max(1, Math.ceil((problem.details?.retry_after_seconds ?? 60) / 60))
    return `You have asked a lot of questions this hour. Please try again in about ${minutes} minute${minutes === 1 ? '' : 's'}.`
  }
  if (problem?.code === 'qa_busy') return 'Your previous question is still being answered. Please wait a moment.'
  if (problem?.code === 'question_too_long') return problem.message ?? 'Please shorten your question.'
  return failure instanceof Error ? failure.message : 'Your question could not be sent. Please try again.'
}

// policy.md is hard-wrapped Markdown: drop the marks and join the lines of a paragraph.
export function plainPolicy(text: string): string {
  return text.replace(/\*\*/g, '').replace(/^#+\s*/gm, '').replace(/([^\n])\n(?!\n)/g, '$1 ')
}

function SourceChips({ sources, onOpenCase }: { sources: AskSource[]; onOpenCase?: (id: string) => void }) {
  const [open, setOpen] = useState<string | null>(null)
  if (!sources.length) return null
  const opened = sources.find((s) => `${s.kind}:${s.id}` === open)
  return (
    <div className="source-area">
      <p className="hint">Sources</p>
      <ul className="source-chips">
        {sources.map((source) => {
          const key = `${source.kind}:${source.id}`
          const label = source.label ?? source.id ?? source.kind
          if (source.kind === 'case' && source.in_history && onOpenCase && source.id) {
            const id = source.id
            return (
              <li key={key}>
                <button type="button" className="chip" onClick={() => onOpenCase(id)}>
                  {label} <span aria-hidden="true">›</span>
                  <span className="visually-hidden"> (open in My history)</span>
                </button>
              </li>
            )
          }
          if (source.text) {
            return (
              <li key={key}>
                <button type="button" className={open === key ? 'chip active' : 'chip'}
                  aria-expanded={open === key} onClick={() => setOpen(open === key ? null : key)}>
                  {label}
                </button>
              </li>
            )
          }
          return <li key={key}><span className="chip static">{label}</span></li>
        })}
      </ul>
      {opened?.text && (
        <div className="source-text" role="region" aria-label={opened.label ?? 'Source'}>
          {plainPolicy(opened.text)}
        </div>
      )}
    </div>
  )
}

function AnswerCard({ item, onOpenCase, focus }: {
  item: AskAnswer
  onOpenCase?: (id: string) => void
  focus?: boolean
}) {
  const ref = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (focus) ref.current?.focus() }, [focus, item.question_id])
  const refusal = item.kind === 'refusal'
  // The heading already says it; the text starts with the reason instead.
  const rest = refusal ? item.answer.replace(/^I can['’]t answer that[:.]?\s*/, '') : item.answer
  const text = rest.charAt(0).toUpperCase() + rest.slice(1)
  return (
    <article className={refusal ? 'question-card answer-card refusal' : 'question-card answer-card'}
      aria-labelledby={`answer-${item.question_id}`}>
      <div className="card-top">
        <span className={refusal ? 'state-tag' : 'state-tag done'}>{item.label}</span>
      </div>
      <p className="hint asked">You asked: “{item.question}”</p>
      <h2 id={`answer-${item.question_id}`} ref={ref} tabIndex={-1} className="answer-title">
        {refusal ? 'I can’t answer that' : 'Answer'}
      </h2>
      <p className="answer-text">{text}</p>
      {!refusal && <SourceChips sources={item.sources} onOpenCase={onOpenCase} />}
      {item.source === 'template' && (
        <p className="hint">Built from your records by the system{item.reason === 'llm_unavailable' || item.reason === 'llm_disabled' ? '' : ' (the AI answer was not used)'}.</p>
      )}
    </article>
  )
}

export function WorkerAsk({ onOpenCase }: { onOpenCase?: (id: string) => void }) {
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [current, setCurrent] = useState<AskAnswer | null>(null)
  const [earlier, setEarlier] = useState<AskAnswer[] | null>(null)
  const [limits, setLimits] = useState<AskLimits | null>(null)
  const [loadError, setLoadError] = useState('')
  const max = limits?.max_chars ?? DEFAULT_MAX

  useEffect(() => {
    const controller = new AbortController()
    getAskHistory(controller.signal)
      .then((history) => {
        if (controller.signal.aborted) return
        setEarlier(history.items)
        setLimits(history.limits)
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) {
          setEarlier([])
          setLoadError(failure instanceof Error ? failure.message : 'Your earlier questions could not be loaded.')
        }
      })
    return () => controller.abort()
  }, [])

  async function submit(text: string) {
    const trimmed = text.trim()
    if (trimmed.length < 3 || busy) return
    setBusy(true)
    setError('')
    try {
      const result = await askQuestion(trimmed)
      if (current) setEarlier((list) => [current, ...(list ?? [])])
      setCurrent(result)
      setLimits(result.limits)
      setQuestion('')
    } catch (failure) {
      setError(errorText(failure))
    } finally {
      setBusy(false)
    }
  }

  const left = limits?.questions_left_this_hour
  const shown = (earlier ?? []).filter((item) => item.question_id !== current?.question_id).slice(0, 5)
  return (
    <section aria-label="Ask" className="ask-view">
      <form className="question-card ask-form" onSubmit={(event) => { event.preventDefault(); void submit(question) }}>
        <label htmlFor="ask-question">Ask about your attendance</label>
        <textarea id="ask-question" value={question} rows={3} maxLength={max}
          enterKeyHint="send" disabled={busy} aria-describedby="ask-help ask-count"
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit(question) }
          }} />
        <div className="ask-meta">
          <p className="hint" id="ask-help">Your leave, schedule, punches, cases or the policy. Answers never change anything.</p>
          <p className="hint count" id="ask-count" aria-live="polite">{question.length} / {max}</p>
        </div>
        <div className="actions stack">
          <button type="submit" disabled={busy || question.trim().length < 3}>{busy ? 'Checking…' : 'Send'}</button>
        </div>
        <p className="hint">Try one of these:</p>
        <ul className="suggestions">
          {SUGGESTIONS.map((text) => (
            <li key={text}>
              <button type="button" className="secondary chip-button" disabled={busy}
                onClick={() => { setQuestion(text); void submit(text) }}>{text}</button>
            </li>
          ))}
        </ul>
        {typeof left === 'number' && (
          <p className="hint">{left} question{left === 1 ? '' : 's'} left this hour.</p>
        )}
      </form>

      {busy && <p role="status" className="panel">Checking your records…</p>}
      {error && <p role="alert" className="error panel">{error}</p>}
      {current && <AnswerCard item={current} onOpenCase={onOpenCase} focus />}

      {loadError && <p className="hint">{loadError}</p>}
      {shown.length > 0 && (
        <section aria-label="Earlier questions">
          <h2 className="earlier-title">Earlier questions</h2>
          {shown.map((item) => <AnswerCard key={item.question_id} item={item} onOpenCase={onOpenCase} />)}
        </section>
      )}
    </section>
  )
}
