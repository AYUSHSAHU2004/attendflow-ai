import { Fragment, useEffect, useRef, useState } from 'react'
import { ApiError, getBriefing, refreshBriefing, type Briefing } from './api'

// Phase 17: the daily briefing at the top of /admin (all teams) and /supervisor (own team).
// Reading never calls the LLM. When the stored briefing is out of date the card asks for
// one refresh by itself (only if an LLM is configured and the server allows it).

const CASE_ID = /(P\d{1,2}-E\d{3}-\d{4}-\d{2}-\d{2}(?:-[A-Za-z0-9]+)*)/g

function shortTime(value: string) {
  return value.slice(0, 16).replace('T', ' ')
}

function waitText(seconds: number | null | undefined) {
  if (!seconds) return 'later'
  const minutes = Math.ceil(seconds / 60)
  return minutes >= 60 ? 'tomorrow' : `in ${minutes} min`
}

function refreshProblem(failure: unknown): string {
  if (failure instanceof ApiError) {
    const wait = (failure.details as { retry_after_seconds?: number } | null)?.retry_after_seconds
    if (failure.code === 'briefing_too_soon') return `Refresh is available again ${waitText(wait)}.`
    if (failure.code === 'briefing_daily_cap') return 'Today\'s briefing budget is used up. The template stays current.'
    if (failure.code === 'briefing_busy') return 'A briefing is being written right now; it appears here in a moment.'
    return failure.message
  }
  return 'The briefing could not be refreshed.'
}

// The case opens in the page's own detail panel; bring it into view once it renders.
function scrollToCase(tries = 20) {
  const card = document.querySelector('.case-card')
  if (card) card.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  else if (tries > 0) window.setTimeout(() => scrollToCase(tries - 1), 100)
}

function CaseLink({ id, onOpenCase }: { id: string; onOpenCase: (id: string) => void }) {
  return (
    <button type="button" className="case-chip" onClick={() => { onOpenCase(id); scrollToCase() }}
      aria-label={`Open case ${id}`}>
      {id}
    </button>
  )
}

function Linked({ text, onOpenCase }: { text: string; onOpenCase: (id: string) => void }) {
  const parts = text.split(CASE_ID)
  return (
    <>
      {parts.map((part, index) => index % 2 === 1
        ? <CaseLink key={index} id={part} onOpenCase={onOpenCase} />
        : <Fragment key={index}>{part}</Fragment>)}
    </>
  )
}

export function BriefingCard({ actor, onOpenCase }: { actor: string; onOpenCase: (id: string) => void }) {
  const [briefing, setBriefing] = useState<Briefing | null>(null)
  const [error, setError] = useState('')
  const [problem, setProblem] = useState('')
  const [busy, setBusy] = useState(false)
  const [load, setLoad] = useState(0)
  const autoAsked = useRef(false)

  async function refresh() {
    setBusy(true)
    setProblem('')
    try {
      setBriefing(await refreshBriefing(actor))
    } catch (failure) {
      setProblem(refreshProblem(failure))
      // Someone else (another tab or the scheduler) is writing it: show theirs shortly.
      if (failure instanceof ApiError && failure.code === 'briefing_busy') {
        window.setTimeout(() => { setProblem(''); setLoad((value) => value + 1) }, 4000)
      }
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    getBriefing(actor, controller.signal)
      .then((body) => {
        if (controller.signal.aborted) return
        setBriefing(body)
        setError('')
        const r = body.refresh
        if (body.stale && r.allowed && r.llm_configured && !autoAsked.current) {
          autoAsked.current = true
          void refresh()
        }
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) {
          setError(failure instanceof Error ? failure.message : 'The briefing could not be loaded.')
        }
      })
    return () => controller.abort()
  }, [actor, load])

  if (error) {
    return (
      <section className="panel briefing-card" aria-label="Daily briefing">
        <h2>Today's briefing</h2>
        <p role="alert" className="error">{error}</p>
        <button className="secondary small" onClick={() => { setError(''); setLoad(load + 1) }}>Try again</button>
      </section>
    )
  }
  if (briefing === null) {
    return (
      <section className="panel briefing-card" aria-label="Daily briefing">
        <h2>Today's briefing</h2>
        <p role="status">Loading the briefing…</p>
      </section>
    )
  }
  const r = briefing.refresh
  const scope = briefing.scope === 'all' ? 'All teams' : `${briefing.team ?? 'Your'} team`
  return (
    <section className="panel briefing-card" aria-labelledby="briefing-title" aria-busy={busy}>
      <div className="briefing-head">
        <h2 id="briefing-title">Today's briefing <span className="hint">· {scope}</span></h2>
        <span className={briefing.source === 'llm' ? 'source-tag llm' : 'source-tag'}>
          {briefing.label}
        </span>
      </div>
      <p className="briefing-headline"><Linked text={briefing.headline} onOpenCase={onOpenCase} /></p>
      {briefing.sections.map((section) => (
        <div key={section.key} className="briefing-section">
          <h3>{section.title}</h3>
          <ul>
            {section.bullets.map((bullet, index) => (
              <li key={index}>
                <Linked text={bullet.text} onOpenCase={onOpenCase} />
                {bullet.case_ids.filter((id) => !bullet.text.includes(id)).map((id) => (
                  <Fragment key={id}> <CaseLink id={id} onOpenCase={onOpenCase} /></Fragment>
                ))}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {briefing.team_lines.length > 0 && (
        <div className="briefing-section">
          <h3>{briefing.scope === 'all' ? 'Teams' : 'Your team'}</h3>
          <ul>
            {briefing.team_lines.map((line) => (
              <li key={line.team}><strong>{line.team}:</strong> <Linked text={line.text} onOpenCase={onOpenCase} /></li>
            ))}
          </ul>
        </div>
      )}
      <div className="briefing-foot">
        <p className="hint">
          {briefing.stored ? 'Written' : 'Built'} {shortTime(briefing.generated_at)} (workflow time)
          {briefing.llm_calls > 0 && ` · ${briefing.llm_calls} LLM call${briefing.llm_calls === 1 ? '' : 's'}`}
          {briefing.failed_checks.length > 0 && ` · failed checks: ${briefing.failed_checks.join(', ')}`}
        </p>
        <button className="secondary small" onClick={() => void refresh()} disabled={busy || !r.allowed}>
          {busy ? 'Writing…' : 'Refresh'}
        </button>
      </div>
      {busy && <p role="status" className="hint">Writing a fresh briefing from the current facts…</p>}
      {!busy && !r.allowed && !problem && (
        <p className="hint">{r.reason === 'daily_cap'
          ? 'Today\'s LLM budget is used up; the template stays current.'
          : `Refresh is available again ${waitText(r.retry_after_seconds)}.`}</p>
      )}
      {problem && <p role="alert" className="error">{problem}</p>}
    </section>
  )
}
