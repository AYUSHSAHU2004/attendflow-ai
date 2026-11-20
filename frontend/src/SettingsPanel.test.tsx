import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getRuntimeSettings, type RuntimeSetting, type RuntimeSettings } from './api'
import { SettingsPanel } from './SettingsPanel'

vi.mock('./api', async (importOriginal) => ({
  ...await importOriginal<typeof import('./api')>(),
  getRuntimeSettings: vi.fn(),
}))

function setting(overrides: Partial<RuntimeSetting>): RuntimeSetting {
  return {
    key: 'no_reply_reminder_hours', label: 'No-reply reminder after', group: 'No-reply ladder',
    help: 'Hours of silence before the worker gets one reminder.', kind: 'int', value: 8,
    value_text: '8 h', source: 'default', server_value: 8, default_value: 8,
    env_var: 'NO_REPLY_REMINDER_HOURS', editable: true, minimum: 1, maximum: 72, unit: 'h',
    range_text: 'a whole number from 1 to 72 h', within_range: true,
    needs_confirm_to_enable: false, locked_note: null, last_change: null,
    ...overrides,
  }
}

function view(overrides: Partial<RuntimeSettings> = {}): RuntimeSettings {
  return {
    profile: 'local', changes_allowed: true, locked_reason: null, min_reason_length: 10,
    items: [
      setting({
        value: 12, value_text: '12 h', source: 'override',
        last_change: {
          id: 7, at: '2026-04-16T08:00:00', action: 'settings_changed',
          key: 'no_reply_reminder_hours', label: 'No-reply reminder after', actor_id: 'E201',
          actor_name: 'Priya Sharma', old_value: 8, old_source: 'default', new_value: 12,
          new_source: 'override', old_text: '8 h', new_text: '12 h',
          reason: 'Night shift workers need more time to answer',
        },
      }),
      setting({
        key: 'scheduler_enabled', label: 'Scheduler timer', kind: 'bool', value: false,
        value_text: 'off', editable: false, minimum: null, maximum: null, unit: null,
        range_text: null, locked_note: 'Set by the server configuration.',
      }),
    ],
    ...overrides,
  }
}

describe('SettingsPanel', () => {
  beforeEach(() => { vi.mocked(getRuntimeSettings).mockReset() })

  it('shows value, source, range and the last change, read-only', async () => {
    vi.mocked(getRuntimeSettings).mockResolvedValue(view())
    render(<SettingsPanel />)
    await userEvent.click(screen.getByText('Current settings'))
    const reminder = (await screen.findByRole('rowheader', { name: /No-reply reminder after/ })).closest('tr')!
    const row = within(reminder)
    expect(row.getByText('12 h')).toBeInTheDocument()
    expect(row.getByText('Changed at runtime')).toBeInTheDocument()
    expect(row.getByText('a whole number from 1 to 72 h')).toBeInTheDocument()
    expect(row.getByText(/Changed by Priya Sharma, 2026-04-16 08:00: 8 h → 12 h/)).toBeInTheDocument()
    expect(row.getByText('Reason: Night shift workers need more time to answer')).toBeInTheDocument()
    const timer = within(screen.getByRole('rowheader', { name: /Scheduler timer/ }).closest('tr')!)
    expect(timer.getByText('Server only')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('explains the Locked profile', async () => {
    vi.mocked(getRuntimeSettings).mockResolvedValue(view({
      profile: 'locked', changes_allowed: false,
      locked_reason: 'The Locked demo profile is read-only.',
    }))
    render(<SettingsPanel />)
    expect(await screen.findByText('The Locked demo profile is read-only.')).toBeInTheDocument()
  })

  it('shows a refusal in plain words', async () => {
    const refused = new ApiError(403, 'admin_only', 'only the payroll admin can open the admin view')
    vi.mocked(getRuntimeSettings).mockImplementation(() => Promise.reject(refused))
    render(<SettingsPanel />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/payroll admin/)
  })
})
