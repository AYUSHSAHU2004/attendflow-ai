// Shared test data (not a test file itself).
import type { SchedulerCycle, SchedulerStatus } from './api'

export function cycle(overrides: Partial<SchedulerCycle> = {}): SchedulerCycle {
  return {
    cycle_id: 1,
    trigger: 'run_now',
    status: 'completed',
    as_of: '2026-04-16T08:00:00',
    started_at: '2026-11-19T10:00:00+00:00',
    finished_at: '2026-11-19T10:00:02+00:00',
    duration_ms: 2000,
    backlog: false,
    watermark_audit_id: 40,
    detection: 'ok',
    detected: 17,
    new: 0,
    new_exception_ids: [],
    closed_exception_ids: [],
    investigated: [],
    messages_sent: [],
    skipped_budget: [],
    skipped_message_budget: [],
    skipped_backlog: 16,
    errors: [],
    ...overrides,
  }
}

export function schedulerStatus(overrides: Partial<SchedulerStatus> = {}): SchedulerStatus {
  return {
    enabled_setting: false,
    running: false,
    cycle_in_progress: false,
    interval_seconds: 60,
    investigations_per_cycle: 3,
    messages_per_cycle: 3,
    backlog: false,
    next_run_at: null,
    overlaps_skipped: 0,
    watermark: null,
    last_cycle: null,
    as_of: '2026-04-16T08:00:00',
    demo_mode: false,
    workers: [],
    ...overrides,
  }
}
