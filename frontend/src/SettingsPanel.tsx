import { useEffect, useState } from 'react'
import { getRuntimeSettings, type RuntimeSetting, type RuntimeSettings } from './api'
import { plainError } from './SupervisorPage'

const SOURCE_LABELS: Record<RuntimeSetting['source'], string> = {
  default: 'Default',
  env: 'Server (.env)',
  override: 'Changed at runtime',
}

function changedText(item: RuntimeSetting): string {
  const change = item.last_change
  if (!change) return '—'
  const when = change.at.slice(0, 16).replace('T', ' ')
  const verb = change.action === 'settings_reset' ? 'Reset' : 'Changed'
  const who = change.actor_name ?? change.actor_id ?? 'someone'
  return `${verb} by ${who}, ${when}: ${change.old_text ?? '?'} → ${change.new_text ?? '?'}`
}

// Phase 18: a read-only view of the runtime settings. Changing them is Phase 19.
export function SettingsPanel({ refresh = 0 }: { refresh?: number }) {
  const [data, setData] = useState<RuntimeSettings | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    getRuntimeSettings(controller.signal)
      .then((body) => { if (!controller.signal.aborted) { setData(body); setError('') } })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(plainError(failure)) })
    return () => controller.abort()
  }, [refresh])

  if (error) {
    return (
      <section aria-label="Current settings" className="panel settings-panel">
        <p role="alert" className="error">Current settings: {error}</p>
      </section>
    )
  }
  return (
    <details className="panel settings-panel">
      <summary>Current settings</summary>
      {!data && <p role="status">Loading the settings…</p>}
      {data && (
        <>
          <p className="hint">
            {data.changes_allowed
              ? 'Read-only here. Changes go through the settings API and are audited.'
              : data.locked_reason}
          </p>
          <div className="table-scroll">
            <table className="settings-table">
              <thead>
                <tr>
                  <th scope="col">Setting</th>
                  <th scope="col">Value</th>
                  <th scope="col">Source</th>
                  <th scope="col">Allowed</th>
                  <th scope="col">Last change</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.key} className={item.editable ? '' : 'read-only'}>
                    <th scope="row">
                      {item.label}
                      <span className="hint block">{item.key}</span>
                    </th>
                    <td>
                      {item.value_text}
                      {!item.within_range && <span className="hint block">Outside the runtime range</span>}
                    </td>
                    <td><span className={`badge source-${item.source}`}>{SOURCE_LABELS[item.source]}</span></td>
                    <td>{item.editable ? item.range_text ?? 'on or off' : 'Server only'}</td>
                    <td>
                      {changedText(item)}
                      {item.last_change?.reason && (
                        <span className="hint block">Reason: {item.last_change.reason}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </details>
  )
}
