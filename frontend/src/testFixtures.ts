// Shared test data (not a test file itself).
import type { AutoFix, AutoResolveMetric, SchedulerCycle, SchedulerStatus } from './api'

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
    skipped_undone: 0,
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

export function metric(overrides: Partial<AutoResolveMetric> = {}): AutoResolveMetric {
  return {
    resolved_without_human: 1,
    needed_handling: 17,
    percent: 5.9,
    undone: 0,
    closed_by_data_change: 0,
    date_from: null,
    date_to: null,
    auto_resolve_enabled: true,
    allowed_policies: ['P2', 'P7'],
    by_policy: [
      { policy_id: 'P1', needed_handling: 1, auto_resolved: 0, undone: 0, closed_by_data_change: 0 },
      { policy_id: 'P2', needed_handling: 1, auto_resolved: 1, undone: 0, closed_by_data_change: 0 },
    ],
    ...overrides,
  }
}

export function autoFix(overrides: Partial<AutoFix> = {}): AutoFix {
  return {
    state: 'auto_resolved',
    basis: "2 'in' taps 2 min apart, within the 5 min duplicate window",
    held_because: [],
    policy_quote: 'Keep the earliest punch and void the later one. This case is auto-resolved and audit-logged; no approval is needed.',
    changes: ['P0005 clock-in 08:59: voided (kept in the database)'],
    data_changed: true,
    resolved_by: 'system',
    resolved_at: '2026-04-16T08:00:00',
    undone_by: null,
    undone_by_name: null,
    undone_at: null,
    undo_reason: null,
    can_undo: true,
    undo_unavailable_reason: null,
    last_refusal: null,
    ...overrides,
  }
}
