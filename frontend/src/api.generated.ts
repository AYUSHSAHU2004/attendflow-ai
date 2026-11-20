// Generated from FastAPI OpenAPI. Run npm run api:generate.
export interface paths {
    "/api/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health check */
        get: operations["health_api_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/seed": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reset the demo: wipe all tables and reload the CSVs
         * @description Destructive. Disabled when ATTENDFLOW_ENABLE_SEED=false (must be off or protected on a deployed server).
         */
        post: operations["seed_api_seed_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/detection/run": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Run the rule engine on the database and save the exceptions
         * @description Idempotent: exceptions are upserted by their stable ID.
         */
        post: operations["run_detection_api_detection_run_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List exceptions */
        get: operations["list_exceptions_api_exceptions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** One exception with its audit trail */
        get: operations["get_exception_api_exceptions__exception_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/investigate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Investigation */
        post: operations["start_investigation_api_exceptions__exception_id__investigate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/investigate/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Poll Investigation */
        get: operations["poll_investigation_api_exceptions__exception_id__investigate__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve a fix option: applies it and resolves the exception (one transaction)
         * @description Supervisors and the payroll admin only, and only the assignee. After a fix that changed data, detection re-runs so new exceptions it created appear as open cases.
         */
        post: operations["approve_api_exceptions__exception_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/edit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve a fix option with changed params (validated before anything is saved) */
        post: operations["edit_api_exceptions__exception_id__edit_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reject: a supervisor's reject escalates to the payroll admin; the admin's reject is final */
        post: operations["reject_api_exceptions__exception_id__reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/escalate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send the case to the payroll admin without rejecting the fix
         * @description Only the assignee (a supervisor); workers get 403 supervisor_only. The case becomes escalated and assigned to the payroll admin, with the reason in the audit log. No data changes. Used after the no-reply ladder brought the supervisor in (Phase 13), or whenever the supervisor cannot decide.
         */
        post: operations["escalate_api_exceptions__exception_id__escalate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/undo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Undo an auto-resolve: restore the rows, reopen the case for people
         * @description The payroll admin may undo any auto-resolved case; a supervisor only their own team's (else 403 not_assigned); workers get 403 supervisor_only. The rows the auto-resolve changed go back to their stored 'before' values through fixes/apply.py. 409 undo_conflict when a stored row (or this worker's punches that day, by another fix) changed since: nothing changes except an undo_refused audit row. 409 not_auto_resolved / already_undone / undo_unavailable (no snapshot). The case becomes open with the worker's supervisor and is never auto-resolved or handled by the scheduler again.
         */
        post: operations["undo_api_exceptions__exception_id__undo_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/ask-worker": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Hand the case to the worker to confirm what happened */
        post: operations["ask_worker_api_exceptions__exception_id__ask_worker_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/worker-reply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Record the worker's Yes or No and return a receipt */
        post: operations["worker_reply_api_exceptions__exception_id__worker_reply_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/worker-confirm-time": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Worker Confirm Time */
        post: operations["worker_confirm_time_api_exceptions__exception_id__worker_confirm_time_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exceptions/{exception_id}/worker-manual-time": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Worker Manual Time */
        post: operations["worker_manual_time_api_exceptions__exception_id__worker_manual_time_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/worker/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Questions and pending follow-ups for the worker */
        get: operations["worker_messages_api_worker_messages_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/worker/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * What happened to my cases: my questions, my answers and the outcome
         * @description Worker-only and scoped to the caller's own cases (others get 403 worker_inbox_only). Outcome texts are built by code; no LLM, no writes.
         */
        get: operations["worker_history_api_worker_history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/worker/ask": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ask a short question about your own attendance or the policy
         * @description Worker-only (others get 403 worker_only). The employee is the caller; the question can never widen that. Code refuses questions about other people, pay, changes or other topics with no LLM call. Otherwise code picks the facts (own leave balance, schedule, punches, cases, policy text) and at most three LLM calls phrase the answer (intent pick only when needed, answer, one correction after a failed check); every number, date, ID and name is checked, else the template answer. 422 question_too_long, 429 qa_rate_limited (QA_QUESTIONS_PER_HOUR), 409 qa_busy. Changes no timecard, schedule or leave.
         */
        post: operations["worker_ask_api_worker_ask_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/worker/ask/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * My last questions and the answers I was shown
         * @description Worker-only and scoped to the caller. Never calls the LLM and writes nothing.
         */
        get: operations["worker_ask_history_api_worker_ask_history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/worker-questions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Questions workers asked the employee Q&A (payroll admin only, read-only) */
        get: operations["admin_worker_questions_api_admin_worker_questions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/briefing": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * The caller's daily briefing (payroll admin: all teams; supervisor: own team)
         * @description Never calls the LLM and writes nothing. Returns the stored briefing when the facts are unchanged, else a template built from the current facts with stale=true. Workers get 403.
         */
        get: operations["get_briefing_api_briefing_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/briefing/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Write a fresh briefing (at most two LLM calls, else the template)
         * @description One LLM call phrases the code-built facts; if the draft fails a check, one correction request follows; a provider error or timeout uses the template at once. 429 briefing_too_soon within BRIEFING_MIN_INTERVAL_SECONDS of the last briefing for this scope, 429 briefing_daily_cap when the daily call budget is used up, 409 briefing_busy while one is being written. Changes no timecard, schedule or leave.
         */
        post: operations["refresh_briefing_api_briefing_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/supervisor/queue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Cases waiting for the caller's decision
         * @description A supervisor sees their own team's cases assigned to them that are awaiting_supervisor, or open with an investigation routed to the supervisor, plus escalated cases assigned to them. The payroll admin sees escalated cases assigned to them. Cases still waiting for the worker's actual time never appear, unless the no-reply ladder brought the supervisor in (then `no_reply` says how long the worker has been silent). Workers get 403. Sorted by severity (high first), then date, then ID.
         */
        get: operations["supervisor_queue_api_supervisor_queue_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/supervisor/cases/{exception_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * The case card: issue, policy, evidence, worker reply, re-check and fix options
         * @description Only the assignee (a supervisor or the payroll admin) may open it. Evidence rows of other workers are left out and their names are redacted. Every text is stored data or built by code; this endpoint never calls the LLM.
         */
        get: operations["supervisor_case_api_supervisor_cases__exception_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/supervisor/auto-resolved": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Auto-resolved (and undone) P2/P7 cases for the caller's team
         * @description A supervisor sees their own team's; the payroll admin sees all. Each item says what was fixed, why code was allowed to close it, the policy text, and whether the caller may undo it. Workers get 403. Read-only; never calls the LLM.
         */
        get: operations["supervisor_auto_resolved_api_supervisor_auto_resolved_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/metrics/auto-resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * X of Y exceptions resolved without a human (payroll admin only)
         * @description Counted by code from the database. X = auto-resolved and not undone. Y = exceptions that needed handling: all in the date range except those closed because the data changed (no_longer_detected), which are returned as closed_by_data_change. Optional date_from/date_to filter on the exception date.
         */
        get: operations["auto_resolve_metric_api_admin_metrics_auto_resolve_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/dashboard": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read-only operations dashboard for payroll admins and supervisors
         * @description Supervisors only see their own team. Optional dates filter exception dates. Overtime always covers the engine's current week.
         */
        get: operations["operations_dashboard_api_dashboard_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/payroll": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Attendance readiness for one Monday-to-Sunday period */
        get: operations["payroll_readiness_api_payroll_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/payroll/{week_start}/sign-off": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Record a human sign-off for a closed, blocker-free week */
        post: operations["payroll_sign_off_api_payroll__week_start__sign_off_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/payroll/{week_start}/reopen": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reopen a signed-off week with a human reason */
        post: operations["payroll_reopen_api_payroll__week_start__reopen_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/exceptions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Every exception, with counters (payroll admin only)
         * @description Only the payroll admin may call this; everyone else gets 403 admin_only. Counters are counted by the database over every exception and ignore the filters. `q` matches the employee name or ID (case-insensitive). Default sort: severity (high first), then date, then ID. Read-only; never calls the LLM.
         */
        get: operations["admin_exceptions_api_admin_exceptions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/exceptions/{exception_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * One case, read-only: evidence, investigation, worker reply, re-check, audit
         * @description Payroll admin only. The full audit trail is oldest first. Tool calls are listed with their arguments and outcome only (no tool output, prompts or keys). To investigate, use POST /api/exceptions/{id}/investigate; to decide an escalated case, use the supervisor card and decision endpoints.
         */
        get: operations["admin_exception_api_admin_exceptions__exception_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Runtime settings: value, source and range (payroll admin only)
         * @description Every editable setting and the read-only ones, with the effective value, its source (default / env / override), the allowed range and the last change. Payroll admin only (403 admin_only). Works in every profile.
         */
        get: operations["get_runtime_settings_api_settings_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/settings/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Settings changes and resets, newest first (payroll admin only) */
        get: operations["get_settings_history_api_settings_history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/settings/{key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change one runtime setting (payroll admin only)
         * @description Whitelisted keys only (403 setting_locked for configuration, secrets and policy rules; 404 unknown_setting). Needs a reason of 10+ characters. Turning auto_resolve_enabled on needs `confirm: true`. Refused in the deployed Locked profile (403 settings_locked_in_profile). Never retroactive: the scheduler reads the new value at its next cycle and running no-reply waits keep their limits. Audited as settings_changed.
         */
        put: operations["put_setting_api_settings__key__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/settings/{key}/reset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Remove a runtime override: back to the server value (payroll admin only)
         * @description Needs a reason of 10+ characters; 409 no_override when nothing is overridden. Refused in the deployed Locked profile. Audited as settings_reset.
         */
        post: operations["reset_setting_api_settings__key__reset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/activity": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Activity Center feed: what the system, the LLM agent and people did
         * @description The payroll admin sees everything; a supervisor only rows of cases whose worker is on their team (rows without a case are payroll-only); workers get 403. Built from the audit log, newest first, one plain sentence per row from fixed templates (no LLM). Never returns before/after data, tool outputs, prompts or model diagnostics. Page with `before_id` = `next_before_id`.
         */
        get: operations["activity_feed_api_activity_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/activity/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Activity Center summary strip, counted by the database
         * @description The payroll admin sees everything; a supervisor only rows of cases whose worker is on their team (rows without a case are payroll-only); workers get 403. Same scope and filters as the feed (actor type and autonomous/human do not apply). `definitions` lists the audit actions behind each count.
         */
        get: operations["activity_summary_api_activity_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/autonomy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * The Autonomy Table: who may do what, approval, undo and guardrail
         * @description Generated from the registry in activity/autonomy.py (the README section is generated from the same registry). Supervisors and the payroll admin; workers get 403.
         */
        get: operations["autonomy_table_api_autonomy_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/audit-log": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Audit log */
        get: operations["audit_log_api_audit_log_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tool-calls": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Agent tool calls (filled from Phase 5) */
        get: operations["tool_calls_api_tool_calls_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/punches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Mock attendance device: record one punch
         * @description Authenticated by the `X-Device-Key` header (DEVICE_API_KEY), not by an actor. The timestamp is local time with no timezone and may not be after the as-of time. An exact duplicate is 409. The punch is written by the ingest module with a `punch_ingested` audit row; detection then runs for that worker's week. Uses no LLM.
         */
        post: operations["receive_punch_api_punches_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/scheduler": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Scheduler status and the last cycle's summary (payroll admin only) */
        get: operations["scheduler_status_api_admin_scheduler_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/scheduler/run-now": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Run one scheduler cycle now and return its summary (payroll admin only)
         * @description Detection, then investigations of new cases and worker messages within the per-cycle limits. Model-free cycles skip investigation and messaging. 409 scheduler_busy if a cycle is already running.
         */
        post: operations["scheduler_run_now_api_admin_scheduler_run_now_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/scheduler/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Start the timer (runtime only; a restart goes back to SCHEDULER_ENABLED)
         * @description Cases detected from now on count as new for the scheduler.
         */
        post: operations["scheduler_start_api_admin_scheduler_start_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/scheduler/stop": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Stop the timer (a running cycle finishes first) */
        post: operations["scheduler_stop_api_admin_scheduler_stop_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/demo/reset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Demo only: reseed, run detection, and reset the scheduler's 'new case' mark
         * @description Requires demo mode and demo reset enabled. Payroll admin only. Destructive: wipes every table like POST /api/seed.
         */
        post: operations["demo_reset_api_admin_demo_reset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/demo/punch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Demo only: send a simulated device punch
         * @description Exists only when ATTENDFLOW_DEMO_MODE=true. Payroll admin only. Goes through the same ingest module and checks as POST /api/punches, so the device key never has to be in the browser. Audited with via=demo_simulator.
         */
        post: operations["demo_punch_api_admin_demo_punch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/demo/clock": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Demo only: the demo clock (now, the data cut-off, the offset)
         * @description Exists only when ATTENDFLOW_DEMO_MODE=true. Payroll admin only.
         */
        get: operations["demo_clock_get_api_admin_demo_clock_get"];
        put?: never;
        /**
         * Demo only: move the demo clock forward (shows the no-reply timeouts)
         * @description Exists only when ATTENDFLOW_DEMO_MODE=true. Payroll admin only. Forward only, at most 14 days past the as-of time (422 clock_limit), audited as demo_clock_moved. Moves `now` (row stamps, timeouts) but never the data cut-off, so detection is unchanged. It runs nothing: the next scheduler cycle (or Run scheduler now) applies the timeouts. A demo reset puts it back to the as-of time.
         */
        post: operations["demo_clock_move_api_admin_demo_clock_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** ActivityCaseOut */
        ActivityCaseOut: {
            /** Exception Id */
            exception_id: string;
            /** Policy Id */
            policy_id: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Title */
            title: string;
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated";
        };
        /** ActivityCountsOut */
        ActivityCountsOut: {
            /**
             * Investigated
             * @description Cases with a stored investigation
             */
            investigated: number;
            /** Messages Sent */
            messages_sent: number;
            /** Reminders Sent */
            reminders_sent: number;
            /** Auto Resolved */
            auto_resolved: number;
            /** Auto Resolves Undone */
            auto_resolves_undone: number;
            /**
             * Escalated By Silence
             * @description Cases the no-reply ladder handed on
             */
            escalated_by_silence: number;
            /** Human Approvals */
            human_approvals: number;
            /** Decided Without Worker */
            decided_without_worker: number;
            /** Human Rejections */
            human_rejections: number;
            /** Device Punches */
            device_punches: number;
        };
        /** ActivityEmployeeOut */
        ActivityEmployeeOut: {
            /** Employee Id */
            employee_id: string;
            /** Name */
            name: string;
            /** Team */
            team: string | null;
        };
        /** ActivityFeedOut */
        ActivityFeedOut: {
            viewer: components["schemas"]["ActivityViewerOut"];
            /** Items */
            items: components["schemas"]["ActivityItemOut"][];
            /**
             * Next Before Id
             * @description Pass as before_id for the next (older) page; null on the last page
             */
            next_before_id: number | null;
        };
        /** ActivityItemOut */
        ActivityItemOut: {
            /** Id */
            id: number;
            /**
             * At
             * Format: date-time
             * @description Workflow time (the demo clock), not server time
             */
            at: string;
            /**
             * Actor Type
             * @enum {string}
             */
            actor_type: "system" | "agent" | "worker" | "supervisor" | "admin" | "device";
            /** Actor Label */
            actor_label: string;
            /**
             * Actor Name
             * @description The person, or which part of the system acted
             */
            actor_name: string;
            /**
             * Autonomous
             * @description Done by the system, the LLM agent or a device
             */
            autonomous: boolean;
            /** Action */
            action: string;
            /**
             * Capability
             * @description The Autonomy Table row this belongs to
             */
            capability: string | null;
            /**
             * Sentence
             * @description Plain sentence from a fixed template; never LLM text
             */
            sentence: string;
            /**
             * Reason
             * @description A person's own typed reason; null otherwise
             */
            reason: string | null;
            case: components["schemas"]["ActivityCaseOut"] | null;
            employee: components["schemas"]["ActivityEmployeeOut"] | null;
        };
        /** ActivitySummaryOut */
        ActivitySummaryOut: {
            /** Date From */
            date_from: string | null;
            /** Date To */
            date_to: string | null;
            counts: components["schemas"]["ActivityCountsOut"];
            /**
             * Definitions
             * @description The audit actions each count uses
             */
            definitions: {
                [key: string]: string[];
            };
        };
        /** ActivityViewerOut */
        ActivityViewerOut: {
            /** Employee Id */
            employee_id: string;
            /** Role */
            role: string;
        };
        /** AdminAuditEntryOut */
        AdminAuditEntryOut: {
            /** Id */
            id: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Actor
             * @enum {string}
             */
            actor: "system" | "agent" | "worker" | "supervisor" | "admin" | "device";
            /** Actor Id */
            actor_id: string | null;
            /** Actor Name */
            actor_name: string | null;
            /** Action */
            action: string;
            /**
             * Summary
             * @description Built by code from the stored audit row
             */
            summary: string;
            /** Reason */
            reason: string | null;
            /**
             * Before Summary
             * @description Status and assignee before, if recorded
             */
            before_summary: string | null;
            /**
             * After Summary
             * @description Status and assignee after, if recorded
             */
            after_summary: string | null;
        };
        /** AdminCaseOut */
        AdminCaseOut: {
            /** Exception Id */
            exception_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated";
            /** Assigned To */
            assigned_to: string | null;
            /** Assigned To Name */
            assigned_to_name: string | null;
            /** Needs Your Decision */
            needs_your_decision: boolean;
            /**
             * Can Investigate
             * @description True while the case is open
             */
            can_investigate: boolean;
            /** Auto Resolved */
            auto_resolved: boolean;
            /** @description P2/P7 only: the auto-resolve, why, and whether you may undo */
            auto_fix?: components["schemas"]["AutoFixOut"] | null;
            employee: components["schemas"]["CardEmployeeOut"];
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Policy Id */
            policy_id: string;
            /** Title */
            title: string;
            /** Summary */
            summary: string;
            /**
             * Severity
             * @enum {string}
             */
            severity: "low" | "medium" | "high";
            /**
             * Kind
             * @enum {string}
             */
            kind: "breach" | "risk";
            /** Details */
            details: {
                [key: string]: unknown;
            };
            policy: components["schemas"]["CardPolicyOut"];
            /** Evidence */
            evidence: {
                [key: string]: unknown;
            }[];
            /** Options */
            options: components["schemas"]["CardOptionOut"][];
            investigation: components["schemas"]["InvestigationCase"] | null;
            latest_job: components["schemas"]["AdminJobOut"] | null;
            /** Worker Messages */
            worker_messages: components["schemas"]["AdminWorkerMessageOut"][];
            recheck: components["schemas"]["WorkerRecheckOut"] | null;
            /** Applied Fix */
            applied_fix: {
                [key: string]: unknown;
            } | null;
            /**
             * Audit Trail
             * @description Oldest first
             */
            audit_trail: components["schemas"]["AdminAuditEntryOut"][];
            /** Tool Calls */
            tool_calls: components["schemas"]["AdminToolCallOut"][];
            no_reply?: components["schemas"]["NoReplyOut"] | null;
        };
        /** AdminCountersOut */
        AdminCountersOut: {
            /** Total */
            total: number;
            /** Open */
            open: number;
            /** Awaiting Worker */
            awaiting_worker: number;
            /** Awaiting Supervisor */
            awaiting_supervisor: number;
            /** Escalated */
            escalated: number;
            /** Resolved */
            resolved: number;
            /** Rejected */
            rejected: number;
            /**
             * Auto Resolved
             * @description Resolved by policy without a human (P2, P7 grace)
             */
            auto_resolved: number;
            /**
             * Stuck
             * @description Not final and the no-reply ladder took at least one step (Phase 13)
             * @default 0
             */
            stuck: number;
        };
        /** AdminEmployeeOptionOut */
        AdminEmployeeOptionOut: {
            /** Employee Id */
            employee_id: string;
            /** Name */
            name: string;
            /** Team */
            team: string;
        };
        /** AdminFilterOptionsOut */
        AdminFilterOptionsOut: {
            /** Statuses */
            statuses: ("open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated")[];
            /** Policy Ids */
            policy_ids: string[];
            /** Teams */
            teams: string[];
            /** Employees */
            employees: components["schemas"]["AdminEmployeeOptionOut"][];
            /** Severities */
            severities: ("low" | "medium" | "high")[];
            /** No Reply */
            no_reply?: ("any" | "reminded" | "supervisor" | "payroll_admin" | "waiting")[];
        };
        /** AdminJobOut */
        AdminJobOut: {
            /** Id */
            id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "running" | "completed" | "failed";
            /** Reason */
            reason: string | null;
        };
        /** AdminListItemOut */
        AdminListItemOut: {
            /** Exception Id */
            exception_id: string;
            /** Employee Id */
            employee_id: string;
            /** Employee Name */
            employee_name: string;
            /** Team */
            team: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Policy Id */
            policy_id: string;
            /** Title */
            title: string;
            /** Summary */
            summary: string;
            /**
             * Severity
             * @enum {string}
             */
            severity: "low" | "medium" | "high";
            /**
             * Kind
             * @enum {string}
             */
            kind: "breach" | "risk";
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated";
            /** Auto Resolved */
            auto_resolved: boolean;
            /**
             * Auto Resolve Undone
             * @description A person undid this case's auto-resolve (Phase 12)
             * @default false
             */
            auto_resolve_undone: boolean;
            /** Assigned To */
            assigned_to: string | null;
            /** Assigned To Name */
            assigned_to_name: string | null;
            /**
             * Investigated
             * @description A stored investigation case exists
             */
            investigated: boolean;
            /** Who To Ask */
            who_to_ask: ("worker" | "supervisor" | "hr") | null;
            /**
             * Investigation Fallback
             * @description True when the stored investigation is the engine template
             */
            investigation_fallback: boolean | null;
            /**
             * Needs Your Decision
             * @description Escalated and assigned to the caller
             */
            needs_your_decision: boolean;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            no_reply?: components["schemas"]["NoReplyOut"] | null;
        };
        /** AdminOverviewOut */
        AdminOverviewOut: {
            /** @description Whole database; filters never apply */
            counters: components["schemas"]["AdminCountersOut"];
            /**
             * Matched
             * @description Exceptions matching the filters (before paging)
             */
            matched: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Items */
            items: components["schemas"]["AdminListItemOut"][];
            filter_options: components["schemas"]["AdminFilterOptionsOut"];
        };
        /** AdminQuestionOut */
        AdminQuestionOut: {
            /** Question Id */
            question_id: number;
            /** Question */
            question: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "answer" | "refusal";
            /**
             * Source
             * @enum {string}
             */
            source: "llm" | "template" | "refusal";
            /**
             * Label
             * @description AI answer, Template answer or Can't answer
             */
            label: string;
            /**
             * Reason
             * @description validated, validated_after_retry, validation_failed, llm_error, rate_limited, timeout, no_budget, llm_unavailable, llm_disabled or refused
             */
            reason: string;
            /**
             * Refusal Code
             * @description other_person, pay, action, injection, language, unsupported, out_of_range or ask_supervisor
             */
            refusal_code?: string | null;
            /** Answer */
            answer: string;
            /** Sources */
            sources: components["schemas"]["AskSourceOut"][];
            /** Intents */
            intents: string[];
            /**
             * Asked At
             * Format: date-time
             */
            asked_at: string;
            /** Llm Calls */
            llm_calls: number;
            /** Latency Ms */
            latency_ms?: number | null;
            /** Employee Id */
            employee_id: string;
            /** Employee Name */
            employee_name: string;
            /** Failed Checks */
            failed_checks: string[];
        };
        /** AdminQuestionsOut */
        AdminQuestionsOut: {
            /** Items */
            items: components["schemas"]["AdminQuestionOut"][];
            /** Total */
            total: number;
        };
        /** AdminToolCallOut */
        AdminToolCallOut: {
            /** Run Id */
            run_id: string | null;
            /** Step No */
            step_no: number;
            /** Call No */
            call_no: number | null;
            /** Tool Name */
            tool_name: string;
            /**
             * Input
             * @description Tool arguments: IDs, dates and proposed changes
             */
            input: {
                [key: string]: unknown;
            };
            /** Ok */
            ok: boolean | null;
            /** Error Code */
            error_code: string | null;
            /** Duration Ms */
            duration_ms: number | null;
            /**
             * Result Summary
             * @description One line built by code from the tool output (Phase 14); never the raw output
             */
            result_summary: string;
        };
        /** AdminWorkerMessageOut */
        AdminWorkerMessageOut: {
            /** Id */
            id: number;
            /**
             * Sent At
             * Format: date-time
             */
            sent_at: string;
            /**
             * Source
             * @enum {string}
             */
            source: "llm" | "template";
            /** Message */
            message: string;
            /** Reply Prompt */
            reply_prompt: string;
            /** Confirmed */
            confirmed: boolean | null;
            /**
             * Reply Text
             * @description The worker's own words, unchanged
             */
            reply_text: string | null;
            /** Replied At */
            replied_at: string | null;
            /** Needs Actual Time */
            needs_actual_time: boolean;
            /** Time Review */
            time_review: {
                [key: string]: unknown;
            } | null;
            /** Reminded At */
            reminded_at?: string | null;
            /** Reminder Text */
            reminder_text?: string | null;
        };
        /** ApproveIn */
        ApproveIn: {
            /**
             * Option Id
             * @example set_clock_out_to_scheduled_end
             */
            option_id: string;
            /** Reason */
            reason?: string | null;
            /**
             * Without Worker
             * @description Decide on the evidence without the worker's reply (Phase 13). Only after the no-reply ladder brought the case to you (stage 2 or 3); needs a reason of at least 10 characters
             * @default false
             */
            without_worker: boolean;
            /**
             * Confirm Time Without Worker
             * @description Required with without_worker for an option that sets a punch time: "I'm confirming this time without the worker's reply"
             * @default false
             */
            confirm_time_without_worker: boolean;
        };
        /** ApproveOut */
        ApproveOut: {
            /**
             * Id
             * @example P1-E001-2026-04-14
             */
            id: string;
            /** Employee Id */
            employee_id: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Policy Id */
            policy_id: string;
            /** Title */
            title: string;
            /** Summary */
            summary: string;
            /**
             * Severity
             * @enum {string}
             */
            severity: "low" | "medium" | "high";
            /**
             * Kind
             * @enum {string}
             */
            kind: "breach" | "risk";
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated";
            /** Auto Resolved */
            auto_resolved: boolean;
            /**
             * Auto Resolve Undone At
             * @description Set when a person undid the auto-resolve (Phase 12)
             */
            auto_resolve_undone_at?: string | null;
            /** Auto Resolve Undone By */
            auto_resolve_undone_by?: string | null;
            /**
             * No Reply Stage
             * @description No-reply ladder (Phase 13): 0 none, 1 reminder sent, 2 supervisor brought in, 3 sent to payroll
             * @default 0
             */
            no_reply_stage: number;
            /** No Reply Wait Since */
            no_reply_wait_since?: string | null;
            /** No Reply Reminded At */
            no_reply_reminded_at?: string | null;
            /** No Reply Supervisor At */
            no_reply_supervisor_at?: string | null;
            /** No Reply Admin At */
            no_reply_admin_at?: string | null;
            /** No Reply Late Reply At */
            no_reply_late_reply_at?: string | null;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Evidence */
            evidence: {
                [key: string]: unknown;
            }[];
            /** Fix Options */
            fix_options: components["schemas"]["FixOptionOut"][];
            /** Proposed Fix */
            proposed_fix: {
                [key: string]: unknown;
            } | null;
            worker_recheck?: components["schemas"]["WorkerRecheckOut"] | null;
            /** Applied Fix */
            applied_fix: {
                [key: string]: unknown;
            } | null;
            /**
             * Assigned To
             * @description Whose turn it is to act
             */
            assigned_to: string | null;
            /** Waiting Since */
            waiting_since: string | null;
            /**
             * Last Detected At
             * Format: date-time
             */
            last_detected_at: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Audit Trail */
            audit_trail: components["schemas"]["AuditEntryOut"][];
            investigation_case?: components["schemas"]["InvestigationCase"] | null;
            detection: components["schemas"]["PostFixDetectionOut"];
        };
        /** AskAnswerOut */
        AskAnswerOut: {
            /** Question Id */
            question_id: number;
            /** Question */
            question: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "answer" | "refusal";
            /**
             * Source
             * @enum {string}
             */
            source: "llm" | "template" | "refusal";
            /**
             * Label
             * @description AI answer, Template answer or Can't answer
             */
            label: string;
            /**
             * Reason
             * @description validated, validated_after_retry, validation_failed, llm_error, rate_limited, timeout, no_budget, llm_unavailable, llm_disabled or refused
             */
            reason: string;
            /**
             * Refusal Code
             * @description other_person, pay, action, injection, language, unsupported, out_of_range or ask_supervisor
             */
            refusal_code?: string | null;
            /** Answer */
            answer: string;
            /** Sources */
            sources: components["schemas"]["AskSourceOut"][];
            /** Intents */
            intents: string[];
            /**
             * Asked At
             * Format: date-time
             */
            asked_at: string;
            /** Llm Calls */
            llm_calls: number;
            /** Latency Ms */
            latency_ms?: number | null;
        };
        /** AskHistoryOut */
        AskHistoryOut: {
            /** Items */
            items: components["schemas"]["AskAnswerOut"][];
            limits: components["schemas"]["AskLimitsOut"];
        };
        /** AskIn */
        AskIn: {
            /**
             * Question
             * @description The worker's question in their own words. The server also applies QA_MAX_QUESTION_CHARS (default 300; longer is 422 question_too_long).
             * @example How many sick days do I have left?
             */
            question: string;
        };
        /** AskLimitsOut */
        AskLimitsOut: {
            /** Max Chars */
            max_chars: number;
            /** Questions Per Hour */
            questions_per_hour: number;
            /** Questions Left This Hour */
            questions_left_this_hour: number;
            /** Retry After Seconds */
            retry_after_seconds?: number | null;
            /** Llm Configured */
            llm_configured: boolean;
            /** Llm Calls Left Today */
            llm_calls_left_today: number;
        };
        /** AskResultOut */
        AskResultOut: {
            /** Question Id */
            question_id: number;
            /** Question */
            question: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "answer" | "refusal";
            /**
             * Source
             * @enum {string}
             */
            source: "llm" | "template" | "refusal";
            /**
             * Label
             * @description AI answer, Template answer or Can't answer
             */
            label: string;
            /**
             * Reason
             * @description validated, validated_after_retry, validation_failed, llm_error, rate_limited, timeout, no_budget, llm_unavailable, llm_disabled or refused
             */
            reason: string;
            /**
             * Refusal Code
             * @description other_person, pay, action, injection, language, unsupported, out_of_range or ask_supervisor
             */
            refusal_code?: string | null;
            /** Answer */
            answer: string;
            /** Sources */
            sources: components["schemas"]["AskSourceOut"][];
            /** Intents */
            intents: string[];
            /**
             * Asked At
             * Format: date-time
             */
            asked_at: string;
            /** Llm Calls */
            llm_calls: number;
            /** Latency Ms */
            latency_ms?: number | null;
            limits: components["schemas"]["AskLimitsOut"];
        };
        /** AskSourceOut */
        AskSourceOut: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "policy" | "case" | "leave_balance" | "schedule" | "punches" | "supervisor";
            /**
             * Id
             * @description Policy ID or case ID
             */
            id?: string | null;
            /** Label */
            label?: string | null;
            /**
             * Text
             * @description Code-held detail: the policy.md section, or the case summary and where it is now. Never model text.
             */
            text?: string | null;
            /**
             * In History
             * @description Cases only: the case is in the worker's My history
             */
            in_history?: boolean | null;
        };
        /** AskWorkerIn */
        AskWorkerIn: {
            /** Note */
            note?: string | null;
        };
        /** AuditEntryOut */
        AuditEntryOut: {
            /** Id */
            id: number;
            /** Exception Id */
            exception_id: string | null;
            /**
             * Actor
             * @enum {string}
             */
            actor: "system" | "agent" | "worker" | "supervisor" | "admin" | "device";
            /** Actor Id */
            actor_id: string | null;
            /** Action */
            action: string;
            /** Before */
            before: {
                [key: string]: unknown;
            } | null;
            /** After */
            after: {
                [key: string]: unknown;
            } | null;
            /** Reason */
            reason: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** AuditListOut */
        AuditListOut: {
            /** Count */
            count: number;
            /** Items */
            items: components["schemas"]["AuditEntryOut"][];
        };
        /**
         * AutoFixOut
         * @description An auto-resolve as people see it. Every text is stored data or built by code.
         */
        AutoFixOut: {
            /**
             * State
             * @description held = a candidate left open for a person (unclear, or switched off)
             * @enum {string}
             */
            state: "auto_resolved" | "undone" | "held";
            /**
             * Basis
             * @description Why code was allowed to close it (engine numbers)
             */
            basis: string | null;
            /** Held Because */
            held_because: string[];
            /**
             * Policy Quote
             * @description policy.md "Allowed fixes" for this policy, verbatim
             */
            policy_quote: string;
            /**
             * Changes
             * @description What the auto-resolve changed, one line per row
             */
            changes: string[];
            /** Data Changed */
            data_changed: boolean;
            /** Resolved By */
            resolved_by: "system" | null;
            /** Resolved At */
            resolved_at: string | null;
            /** Undone By */
            undone_by: string | null;
            /** Undone By Name */
            undone_by_name: string | null;
            /** Undone At */
            undone_at: string | null;
            /** Undo Reason */
            undo_reason: string | null;
            /**
             * Can Undo
             * @description The caller may undo it now
             */
            can_undo: boolean;
            /** Undo Unavailable Reason */
            undo_unavailable_reason: string | null;
            last_refusal: components["schemas"]["AutoFixRefusalOut"] | null;
        };
        /** AutoFixRefusalOut */
        AutoFixRefusalOut: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** By */
            by: string | null;
            /** Message */
            message: string | null;
        };
        /** AutoResolveMetricOut */
        AutoResolveMetricOut: {
            /**
             * Resolved Without Human
             * @description X: closed by auto-resolve and not undone
             */
            resolved_without_human: number;
            /**
             * Needed Handling
             * @description Y: exceptions that needed handling (all, minus closed_by_data_change)
             */
            needed_handling: number;
            /**
             * Percent
             * @description 100 * X / Y, one decimal (0 when Y is 0)
             */
            percent: number;
            /**
             * Undone
             * @description Auto-resolves a person undid (counted as human work)
             */
            undone: number;
            /**
             * Closed By Data Change
             * @description Closed as no_longer_detected: the data changed and nobody had to act. Not part of Y.
             */
            closed_by_data_change: number;
            /** Date From */
            date_from: string | null;
            /** Date To */
            date_to: string | null;
            /**
             * Auto Resolve Enabled
             * @description The AUTO_RESOLVE_ENABLED kill switch
             */
            auto_resolve_enabled: boolean;
            /**
             * Allowed Policies
             * @description Policies policy.json lets auto-resolve
             */
            allowed_policies: string[];
            /** By Policy */
            by_policy: components["schemas"]["MetricPolicyOut"][];
        };
        /** AutonomyRowOut */
        AutonomyRowOut: {
            /** Key */
            key: string;
            /** Title */
            title: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "allowed" | "never";
            /**
             * Actor Type
             * @enum {string}
             */
            actor_type: "code" | "llm_agent" | "system" | "device" | "human";
            /** Actor Label */
            actor_label: string;
            /** Performed By */
            performed_by: string;
            /**
             * Approval
             * @enum {string}
             */
            approval: "none" | "supervisor" | "payroll_admin" | "supervisor_or_payroll_admin";
            /** Approval Label */
            approval_label: string;
            /**
             * Reversible
             * @enum {string}
             */
            reversible: "yes_undo" | "no" | "not_applicable";
            /** Reversible Label */
            reversible_label: string;
            /** Guardrail */
            guardrail: string;
            /** Autonomous */
            autonomous: boolean;
            /** Audit Actions */
            audit_actions: string[];
            /** Proof Tests */
            proof_tests: string[];
        };
        /** AutonomyTableOut */
        AutonomyTableOut: {
            /** Items */
            items: components["schemas"]["AutonomyRowOut"][];
        };
        /** BriefingBulletOut */
        BriefingBulletOut: {
            /** Text */
            text: string;
            /** Case Ids */
            case_ids: string[];
        };
        /** BriefingOut */
        BriefingOut: {
            /**
             * Scope
             * @enum {string}
             */
            scope: "all" | "team";
            /** Team */
            team?: string | null;
            /**
             * Source
             * @enum {string}
             */
            source: "llm" | "template";
            /**
             * Reason
             * @description validated, validated_after_retry, validation_failed, llm_error, timeout, llm_unavailable, llm_disabled, no_budget, facts_changed or not_generated
             */
            reason: string;
            /** Label */
            label: string;
            /**
             * Stale
             * @description The facts changed since the stored briefing (or none yet)
             */
            stale: boolean;
            /** Stored */
            stored: boolean;
            /** Briefing Id */
            briefing_id?: number | null;
            /** Headline */
            headline: string;
            /** Sections */
            sections: components["schemas"]["BriefingSectionOut"][];
            /** Team Lines */
            team_lines: components["schemas"]["BriefingTeamLineOut"][];
            /**
             * Generated At
             * Format: date-time
             * @description Workflow time (demo clock)
             */
            generated_at: string;
            /** Facts Hash */
            facts_hash: string;
            /** Llm Calls */
            llm_calls: number;
            /** Latency Ms */
            latency_ms?: number | null;
            /**
             * Failed Checks
             * @description Codes of checks the LLM drafts failed
             */
            failed_checks: string[];
            refresh: components["schemas"]["BriefingRefreshStateOut"];
        };
        /** BriefingRefreshStateOut */
        BriefingRefreshStateOut: {
            /** Allowed */
            allowed: boolean;
            /** Reason */
            reason?: ("too_soon" | "daily_cap") | null;
            /** Retry After Seconds */
            retry_after_seconds?: number | null;
            /** Calls Left Today */
            calls_left_today: number;
            /**
             * Llm Configured
             * @description An LLM key is set and BRIEFING_ENABLED is on
             */
            llm_configured: boolean;
        };
        /** BriefingSectionOut */
        BriefingSectionOut: {
            /**
             * Key
             * @enum {string}
             */
            key: "needs_decision" | "handled_on_its_own" | "blocking_payroll" | "watch";
            /** Title */
            title: string;
            /** Bullets */
            bullets: components["schemas"]["BriefingBulletOut"][];
        };
        /** BriefingTeamLineOut */
        BriefingTeamLineOut: {
            /** Team */
            team: string;
            /** Text */
            text: string;
        };
        /** CardConfirmedTimeOut */
        CardConfirmedTimeOut: {
            /** Timestamp */
            timestamp: string;
            /** Approximate */
            approximate: boolean;
            /** Source */
            source: ("yes" | "llm" | "manual") | null;
            /** Option Id */
            option_id: string | null;
        };
        /** CardConsequenceOut */
        CardConsequenceOut: {
            /**
             * Source
             * @enum {string}
             */
            source: "worker_recheck" | "investigation" | "decision_only" | "unchecked";
            /**
             * Note
             * @description Built by code from the stored re-check; never LLM text
             */
            note: string;
            /** Creates Violations */
            creates_violations: boolean;
            /** New Violations */
            new_violations: components["schemas"]["Finding"][];
            /** Resolved */
            resolved: components["schemas"]["Finding"][];
            /** Day Worked Hours */
            day_worked_hours: number | null;
            /** Week Projected Hours */
            week_projected_hours: number | null;
            /** Weekly Limit Hours */
            weekly_limit_hours: number | null;
        };
        /** CardEmployeeOut */
        CardEmployeeOut: {
            /** Employee Id */
            employee_id: string;
            /** Name */
            name: string;
            /** Team */
            team: string;
        };
        /** CardFieldOut */
        CardFieldOut: {
            /** Name */
            name: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "datetime" | "date" | "time" | "number" | "text" | "fixed";
            /** Value */
            value: unknown;
            /** Editable */
            editable: boolean;
            /** Locked Reason */
            locked_reason?: string | null;
        };
        /** CardInvestigationOut */
        CardInvestigationOut: {
            /** What Happened */
            what_happened: string | null;
            /** Confidence */
            confidence: ("low" | "medium" | "high") | null;
            /** Fallback */
            fallback: boolean;
            /** Who To Ask */
            who_to_ask: ("worker" | "supervisor" | "hr") | null;
            /** Next Action */
            next_action: string | null;
            /** Evidence */
            evidence: {
                [key: string]: unknown;
            }[];
        };
        /** CardOptionOut */
        CardOptionOut: {
            /** Option Id */
            option_id: string;
            /** Action */
            action: string;
            /** Label */
            label: string;
            /** Description */
            description: string;
            /** Params */
            params: {
                [key: string]: unknown;
            };
            /** Decision Only */
            decision_only: boolean;
            /** Requires Worker Confirmation */
            requires_worker_confirmation: boolean;
            /** Worker Confirmed */
            worker_confirmed: boolean;
            /**
             * Note Field
             * @description Decision-only options: the required note param
             */
            note_field: string | null;
            /** Fields */
            fields: components["schemas"]["CardFieldOut"][];
            /**
             * Punches
             * @description edit_punches: the punches whose times may be changed
             */
            punches: components["schemas"]["CardPunchOut"][] | null;
            consequence: components["schemas"]["CardConsequenceOut"];
        };
        /** CardPolicyOut */
        CardPolicyOut: {
            /** Policy Id */
            policy_id: string;
            /** Title */
            title: string;
            /** Rule */
            rule: string;
            /**
             * Cited Text
             * @description The investigation's verbatim quote, else the rule
             */
            cited_text: string;
        };
        /** CardPunchOut */
        CardPunchOut: {
            /** Punch Id */
            punch_id: string;
            /** Type */
            type: string | null;
            /** Timestamp */
            timestamp: string | null;
        };
        /** CardWorkerOut */
        CardWorkerOut: {
            /** Replied */
            replied: boolean;
            /** Confirmed */
            confirmed: boolean | null;
            /**
             * Reply Text
             * @description The worker's own words, unchanged
             */
            reply_text: string | null;
            /** Replied At */
            replied_at: string | null;
            /** Needs Actual Time */
            needs_actual_time: boolean;
        };
        /** CycleBriefingOut */
        CycleBriefingOut: {
            /**
             * Status
             * @enum {string}
             */
            status: "generated" | "fallback" | "skipped";
            /** Reason */
            reason: string;
            /** Briefing Id */
            briefing_id?: number | null;
            /**
             * Llm Calls
             * @default 0
             */
            llm_calls: number;
        };
        /** CycleErrorOut */
        CycleErrorOut: {
            /** Exception Id */
            exception_id: string | null;
            /**
             * Step
             * @enum {string}
             */
            step: "detection" | "investigate" | "ask_worker" | "no_reply" | "briefing";
            /** Error */
            error: string;
        };
        /** CycleInvestigationOut */
        CycleInvestigationOut: {
            /** Exception Id */
            exception_id: string;
            /** Job Id */
            job_id: string;
            /**
             * Job Status
             * @enum {string}
             */
            job_status: "running" | "completed" | "failed";
            /** Reason */
            reason: string | null;
            /**
             * Fallback
             * @description True when the engine template was stored
             */
            fallback: boolean;
            /** Who To Ask */
            who_to_ask: string | null;
            /** Duration Ms */
            duration_ms: number | null;
        };
        /** CycleNoReplyOut */
        CycleNoReplyOut: {
            /**
             * Enabled
             * @default true
             */
            enabled: boolean;
            /** Reminded */
            reminded?: string[];
            /** To Supervisor */
            to_supervisor?: string[];
            /** To Admin */
            to_admin?: string[];
        };
        /** DashboardAgingOut */
        DashboardAgingOut: {
            /** Limits Hours */
            limits_hours: number[];
            /** Case Age */
            case_age: number[];
            /** Waiting Age */
            waiting_age: number[];
        };
        /** DashboardOut */
        DashboardOut: {
            /**
             * Scope
             * @enum {string}
             */
            scope: "all" | "team";
            /**
             * Workflow Now
             * Format: date-time
             */
            workflow_now: string;
            /** Active Total */
            active_total: number;
            /** Stuck */
            stuck: number;
            /** By Status */
            by_status: {
                [key: string]: number;
            };
            /** By Severity */
            by_severity: {
                [key: string]: number;
            };
            /** By Policy */
            by_policy: {
                [key: string]: number;
            };
            /** Ladder */
            ladder: {
                [key: string]: number;
            };
            aging: components["schemas"]["DashboardAgingOut"];
            /** Workload */
            workload: components["schemas"]["DashboardWorkloadOut"][];
            overtime: components["schemas"]["DashboardOvertimeOut"];
            auto_resolve: components["schemas"]["AutoResolveMetricOut"];
        };
        /** DashboardOvertimeOut */
        DashboardOvertimeOut: {
            /**
             * Week Start
             * Format: date
             */
            week_start: string;
            /**
             * Week End
             * Format: date
             */
            week_end: string;
            /** Limit Hours */
            limit_hours: number;
            /** Warning Margin Hours */
            warning_margin_hours: number;
            /** Workers */
            workers: components["schemas"]["DashboardOvertimeWorkerOut"][];
        };
        /** DashboardOvertimeWorkerOut */
        DashboardOvertimeWorkerOut: {
            /** Employee Id */
            employee_id: string;
            /** Employee Name */
            employee_name: string;
            /** Worked Hours */
            worked_hours: number;
            /** Scheduled Remaining Hours */
            scheduled_remaining_hours: number;
            /** Projected Hours */
            projected_hours: number;
            /**
             * Level
             * @enum {string}
             */
            level: "approaching" | "at_limit" | "projected_over" | "already_over";
        };
        /** DashboardWorkloadOut */
        DashboardWorkloadOut: {
            /** Supervisor Id */
            supervisor_id: string | null;
            /** Supervisor Name */
            supervisor_name: string;
            /** Active */
            active: number;
            /** Awaiting Worker */
            awaiting_worker: number;
            /** Awaiting Supervisor */
            awaiting_supervisor: number;
        };
        /** DemoClockIn */
        DemoClockIn: {
            /**
             * Hours
             * @description Move the demo clock forward this much
             */
            hours: number;
        };
        /** DemoClockOut */
        DemoClockOut: {
            /**
             * Now
             * Format: date-time
             * @description The clock's 'now': stamps rows and drives timeouts
             */
            now: string;
            /**
             * Data As Of
             * Format: date-time
             * @description The data cut-off (ATTENDFLOW_AS_OF); moving the demo clock never moves it
             */
            data_as_of: string;
            /** Offset Hours */
            offset_hours: number;
            /** Max Offset Hours */
            max_offset_hours: number;
            /**
             * Movable
             * @description True only in demo mode
             */
            movable: boolean;
            /** Hint */
            hint?: string | null;
        };
        /**
         * DemoPunchIn
         * @description A simulated device punch from the /admin demo panel (DEMO_MODE only).
         */
        DemoPunchIn: {
            /**
             * Employee Id
             * @example E004
             */
            employee_id: string;
            /**
             * Timestamp
             * @description Local time, no timezone, e.g. 2026-04-15T09:02 (seconds optional)
             * @example 2026-04-15T09:02
             */
            timestamp: string;
            /**
             * Type
             * @enum {string}
             */
            type: "in" | "out" | "break_start" | "break_end";
            /**
             * Source
             * @default device
             * @constant
             */
            source: "device";
            /**
             * Device Id
             * @description Defaults to the worker's usual device
             */
            device_id?: string | null;
            /**
             * Location
             * @description One of the known locations; defaults to the worker's usual one
             */
            location?: string | null;
        };
        /** DemoResetOut */
        DemoResetOut: {
            seed: components["schemas"]["SeedOut"];
            detection: components["schemas"]["DetectionRunOut"];
            /** Watermark Audit Id */
            watermark_audit_id: number;
            clock: components["schemas"]["DemoClockOut"];
        };
        /** DemoWorkerOut */
        DemoWorkerOut: {
            /** Employee Id */
            employee_id: string;
            /** Name */
            name: string;
            /** Team */
            team: string;
        };
        /** DetectionRunOut */
        DetectionRunOut: {
            /** As Of */
            as_of: string;
            /** Policy Version */
            policy_version: string;
            /**
             * Found
             * @description Exceptions the engine found in this run
             */
            found: number;
            /** Created */
            created: number;
            /**
             * Updated
             * @description Open exceptions whose numbers changed
             */
            updated: number;
            /** Unchanged */
            unchanged: number;
            /**
             * Options Added
             * @description Cases already in progress that got fix options their policy lacked before
             */
            options_added: number;
            /** Auto Resolved */
            auto_resolved: number;
            /**
             * Auto Resolve Held
             * @description New P2/P7 cases left open for a person (unclear, or the kill switch is off)
             * @default 0
             */
            auto_resolve_held: number;
            /** Closed No Longer Detected */
            closed_no_longer_detected: string[];
            /** By Policy */
            by_policy: {
                [key: string]: number;
            };
            /** Exception Ids */
            exception_ids: string[];
            /**
             * Created Ids
             * @description Exceptions this run stored for the first time
             */
            created_ids?: string[];
        };
        /** DetectionScopeOut */
        DetectionScopeOut: {
            /** Employee Id */
            employee_id: string;
            /**
             * Start
             * Format: date
             */
            start: string;
            /**
             * End
             * Format: date
             */
            end: string;
        };
        /** EditIn */
        EditIn: {
            /**
             * Option Id
             * @example set_clock_out_to_scheduled_end
             */
            option_id: string;
            /**
             * Params
             * @description Only the params to change; they are merged onto the option's params
             * @example {
             *       "timestamp": "2026-04-14T17:30"
             *     }
             */
            params: {
                [key: string]: unknown;
            };
            /**
             * Reason
             * @example Amit left at 17:30
             */
            reason: string;
            /**
             * Without Worker
             * @description Decide on the evidence without the worker's reply (Phase 13). Only after the no-reply ladder brought the case to you (stage 2 or 3); needs a reason of at least 10 characters
             * @default false
             */
            without_worker: boolean;
            /**
             * Confirm Time Without Worker
             * @description Required with without_worker for an option that sets a punch time: "I'm confirming this time without the worker's reply"
             * @default false
             */
            confirm_time_without_worker: boolean;
        };
        /** ErrorBody */
        ErrorBody: {
            /**
             * Code
             * @example invalid_transition
             */
            code: string;
            /**
             * Message
             * @example reject: the exception is already resolved (final)
             */
            message: string;
            /** Details */
            details?: unknown;
        };
        /** ErrorResponse */
        ErrorResponse: {
            error: components["schemas"]["ErrorBody"];
        };
        /** EscalateIn */
        EscalateIn: {
            /**
             * Reason
             * @description Why the case goes to payroll (at least 10 characters, saved in the audit)
             * @example The worker is on leave and I cannot verify the time
             */
            reason: string;
        };
        /** EvidenceFact */
        EvidenceFact: {
            /** Fact */
            fact: string;
            /** Source */
            source: string;
        };
        /** ExceptionDetailOut */
        ExceptionDetailOut: {
            /**
             * Id
             * @example P1-E001-2026-04-14
             */
            id: string;
            /** Employee Id */
            employee_id: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Policy Id */
            policy_id: string;
            /** Title */
            title: string;
            /** Summary */
            summary: string;
            /**
             * Severity
             * @enum {string}
             */
            severity: "low" | "medium" | "high";
            /**
             * Kind
             * @enum {string}
             */
            kind: "breach" | "risk";
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated";
            /** Auto Resolved */
            auto_resolved: boolean;
            /**
             * Auto Resolve Undone At
             * @description Set when a person undid the auto-resolve (Phase 12)
             */
            auto_resolve_undone_at?: string | null;
            /** Auto Resolve Undone By */
            auto_resolve_undone_by?: string | null;
            /**
             * No Reply Stage
             * @description No-reply ladder (Phase 13): 0 none, 1 reminder sent, 2 supervisor brought in, 3 sent to payroll
             * @default 0
             */
            no_reply_stage: number;
            /** No Reply Wait Since */
            no_reply_wait_since?: string | null;
            /** No Reply Reminded At */
            no_reply_reminded_at?: string | null;
            /** No Reply Supervisor At */
            no_reply_supervisor_at?: string | null;
            /** No Reply Admin At */
            no_reply_admin_at?: string | null;
            /** No Reply Late Reply At */
            no_reply_late_reply_at?: string | null;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Evidence */
            evidence: {
                [key: string]: unknown;
            }[];
            /** Fix Options */
            fix_options: components["schemas"]["FixOptionOut"][];
            /** Proposed Fix */
            proposed_fix: {
                [key: string]: unknown;
            } | null;
            worker_recheck?: components["schemas"]["WorkerRecheckOut"] | null;
            /** Applied Fix */
            applied_fix: {
                [key: string]: unknown;
            } | null;
            /**
             * Assigned To
             * @description Whose turn it is to act
             */
            assigned_to: string | null;
            /** Waiting Since */
            waiting_since: string | null;
            /**
             * Last Detected At
             * Format: date-time
             */
            last_detected_at: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Audit Trail */
            audit_trail: components["schemas"]["AuditEntryOut"][];
            investigation_case?: components["schemas"]["InvestigationCase"] | null;
        };
        /** ExceptionListOut */
        ExceptionListOut: {
            /** Count */
            count: number;
            /** Items */
            items: components["schemas"]["ExceptionOut"][];
        };
        /** ExceptionOut */
        ExceptionOut: {
            /**
             * Id
             * @example P1-E001-2026-04-14
             */
            id: string;
            /** Employee Id */
            employee_id: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Policy Id */
            policy_id: string;
            /** Title */
            title: string;
            /** Summary */
            summary: string;
            /**
             * Severity
             * @enum {string}
             */
            severity: "low" | "medium" | "high";
            /**
             * Kind
             * @enum {string}
             */
            kind: "breach" | "risk";
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated";
            /** Auto Resolved */
            auto_resolved: boolean;
            /**
             * Auto Resolve Undone At
             * @description Set when a person undid the auto-resolve (Phase 12)
             */
            auto_resolve_undone_at?: string | null;
            /** Auto Resolve Undone By */
            auto_resolve_undone_by?: string | null;
            /**
             * No Reply Stage
             * @description No-reply ladder (Phase 13): 0 none, 1 reminder sent, 2 supervisor brought in, 3 sent to payroll
             * @default 0
             */
            no_reply_stage: number;
            /** No Reply Wait Since */
            no_reply_wait_since?: string | null;
            /** No Reply Reminded At */
            no_reply_reminded_at?: string | null;
            /** No Reply Supervisor At */
            no_reply_supervisor_at?: string | null;
            /** No Reply Admin At */
            no_reply_admin_at?: string | null;
            /** No Reply Late Reply At */
            no_reply_late_reply_at?: string | null;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Evidence */
            evidence: {
                [key: string]: unknown;
            }[];
            /** Fix Options */
            fix_options: components["schemas"]["FixOptionOut"][];
            /** Proposed Fix */
            proposed_fix: {
                [key: string]: unknown;
            } | null;
            worker_recheck?: components["schemas"]["WorkerRecheckOut"] | null;
            /** Applied Fix */
            applied_fix: {
                [key: string]: unknown;
            } | null;
            /**
             * Assigned To
             * @description Whose turn it is to act
             */
            assigned_to: string | null;
            /** Waiting Since */
            waiting_since: string | null;
            /**
             * Last Detected At
             * Format: date-time
             */
            last_detected_at: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** Finding */
        Finding: {
            /** Policy Id */
            policy_id: string;
            /** Kind */
            kind?: ("breach" | "risk") | null;
            /** Date */
            date: string;
            /** Reason */
            reason: string;
            /** Numbers */
            numbers?: {
                [key: string]: number;
            } | null;
        };
        /** FixOptionOut */
        FixOptionOut: {
            /** Option Id */
            option_id: string;
            /** Action */
            action: string;
            /** Label */
            label: string;
            /**
             * Description
             * @default
             */
            description: string;
            /** Params */
            params: {
                [key: string]: unknown;
            };
            /**
             * Decision Only
             * @description True = changes no timecard, schedule or leave data
             */
            decision_only: boolean;
            /** Policy Id */
            policy_id?: string | null;
            /**
             * Requires Worker Confirmation
             * @description Approve is refused until the worker has confirmed (Yes)
             * @default false
             */
            requires_worker_confirmation: boolean;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HealthOut */
        HealthOut: {
            /**
             * Status
             * @enum {string}
             */
            status: "ok" | "degraded";
            /**
             * Database
             * @enum {string}
             */
            database: "ok" | "unreachable";
            /**
             * As Of
             * Format: date-time
             * @description The demo 'now' (ATTENDFLOW_AS_OF), never the server clock
             */
            as_of: string;
            /** Policy Version */
            policy_version: string;
            /** Version */
            version: string;
        };
        /** InvestigationCase */
        InvestigationCase: {
            /** What Happened */
            what_happened: string;
            /** Policy Id */
            policy_id: string;
            /** Policy Text Cited */
            policy_text_cited: string;
            /** Evidence */
            evidence: components["schemas"]["EvidenceFact"][];
            proposed_fix: components["schemas"]["ProposedFix"] | null;
            validation_result?: components["schemas"]["RunChecksOut"] | null;
            /**
             * Who To Ask
             * @enum {string}
             */
            who_to_ask: "worker" | "supervisor" | "hr";
            /**
             * Confidence
             * @enum {string}
             */
            confidence: "low" | "medium" | "high";
            /**
             * Fallback
             * @default false
             */
            fallback: boolean;
            /**
             * Tool Steps
             * @default 0
             */
            tool_steps: number;
            /**
             * Duration Ms
             * @default 0
             */
            duration_ms: number;
            /** Next Action */
            next_action: string;
        };
        /** InvestigationJobOut */
        InvestigationJobOut: {
            /** Id */
            id: string;
            /** Exception Id */
            exception_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "running" | "completed" | "failed";
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /**
             * Deadline At
             * Format: date-time
             */
            deadline_at: string;
            /** Finished At */
            finished_at: string | null;
            /** Duration Ms */
            duration_ms: number | null;
            /** Reason */
            reason: string | null;
        };
        /** MetricPolicyOut */
        MetricPolicyOut: {
            /** Policy Id */
            policy_id: string;
            /** Needed Handling */
            needed_handling: number;
            /** Auto Resolved */
            auto_resolved: number;
            /** Undone */
            undone: number;
            /** Closed By Data Change */
            closed_by_data_change: number;
        };
        /**
         * NoReplyOut
         * @description The no-reply ladder on one case (Phase 13). Built by code from stored times.
         */
        NoReplyOut: {
            /**
             * Stage
             * @description 0 none (replied late), 1 reminder, 2 supervisor, 3 payroll
             */
            stage: number;
            /** Stage Key */
            stage_key: ("reminded" | "supervisor" | "payroll_admin") | null;
            /** Label */
            label: string;
            /**
             * Note
             * @example Neha Joshi has not replied for 26 h.
             */
            note: string;
            /** Hours Without Reply */
            hours_without_reply: string | null;
            /** Wait Since */
            wait_since: string | null;
            /** Reminded At */
            reminded_at: string | null;
            /** Supervisor At */
            supervisor_at: string | null;
            /** Admin At */
            admin_at: string | null;
            /** Late Reply At */
            late_reply_at: string | null;
            /** Can Decide Without Worker */
            can_decide_without_worker: boolean;
        };
        /** NoReplySettingsOut */
        NoReplySettingsOut: {
            /** Enabled */
            enabled: boolean;
            /** Reminder Hours */
            reminder_hours: number;
            /** Supervisor Hours */
            supervisor_hours: number;
            /** Admin Hours */
            admin_hours: number;
        };
        /** PayrollReadinessOut */
        PayrollReadinessOut: {
            /**
             * Week Start
             * Format: date
             */
            week_start: string;
            /**
             * Week End
             * Format: date
             */
            week_end: string;
            /**
             * Evaluated Through
             * Format: date
             */
            evaluated_through: string;
            /**
             * Data Cutoff
             * Format: date-time
             */
            data_cutoff: string;
            /** Closed */
            closed: boolean;
            /** Has Data */
            has_data: boolean;
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "ready_with_notes" | "blocked";
            /**
             * Scope
             * @enum {string}
             */
            scope: "all" | "team";
            /** Can Sign */
            can_sign: boolean;
            /** Can Reopen */
            can_reopen: boolean;
            signoff: components["schemas"]["PayrollSignoffOut"] | null;
            exception_counts: components["schemas"]["AdminCountersOut"];
            /** Overtime Limit Hours */
            overtime_limit_hours: number;
            /** Reasons */
            reasons: components["schemas"]["ReadinessReasonOut"][];
            /** Teams */
            teams: components["schemas"]["ReadinessGroupOut"][];
            /** Workers */
            workers: components["schemas"]["ReadinessWorkerOut"][];
        };
        /** PayrollReopenIn */
        PayrollReopenIn: {
            /** Reason */
            reason: string;
        };
        /** PayrollSignoffIn */
        PayrollSignoffIn: {
            /** Note */
            note?: string | null;
        };
        /** PayrollSignoffOut */
        PayrollSignoffOut: {
            /** Signer Name */
            signer_name: string;
            /**
             * Signed At
             * Format: date-time
             */
            signed_at: string;
            /** Note */
            note: string | null;
            /** Reopened At */
            reopened_at: string | null;
            /** Stale */
            stale: boolean;
        };
        /** PostFixDetectionOut */
        PostFixDetectionOut: {
            /**
             * Ran
             * @description False for decision-only fixes, or if detection failed
             */
            ran: boolean;
            /**
             * New Exception Ids
             * @description New open exceptions for this worker that the approved fix created
             */
            new_exception_ids: string[];
            /** Closed Exception Ids */
            closed_exception_ids: string[];
            /** Error */
            error?: string | null;
        };
        /** ProposedFix */
        ProposedFix: {
            /** Option Id */
            option_id: string;
            /** Params */
            params: {
                [key: string]: unknown;
            };
        };
        /** PunchAcceptedOut */
        PunchAcceptedOut: {
            punch: components["schemas"]["PunchOut"];
            detection: components["schemas"]["PunchDetectionOut"];
        };
        /** PunchDetectionOut */
        PunchDetectionOut: {
            /** Ran */
            ran: boolean;
            scope: components["schemas"]["DetectionScopeOut"];
            /** New Exception Ids */
            new_exception_ids: string[];
            /** Closed Exception Ids */
            closed_exception_ids: string[];
            /** Updated */
            updated: number;
            /**
             * Error
             * @description Set when detection failed; the punch is kept
             */
            error: string | null;
        };
        /**
         * PunchIn
         * @description One punch from an attendance device. Times are plain local wall-clock times.
         */
        PunchIn: {
            /**
             * Employee Id
             * @example E004
             */
            employee_id: string;
            /**
             * Timestamp
             * @description Local time, no timezone, e.g. 2026-04-15T09:02 (seconds optional)
             * @example 2026-04-15T09:02
             */
            timestamp: string;
            /**
             * Type
             * @enum {string}
             */
            type: "in" | "out" | "break_start" | "break_end";
            /**
             * Source
             * @default device
             * @constant
             */
            source: "device";
            /**
             * Device Id
             * @description Defaults to the worker's usual device
             */
            device_id?: string | null;
            /**
             * Location
             * @description One of the known locations; defaults to the worker's usual one
             */
            location?: string | null;
        };
        /** PunchOut */
        PunchOut: {
            /** Punch Id */
            punch_id: string;
            /** Employee Id */
            employee_id: string;
            /** Timestamp */
            timestamp: string;
            /**
             * Type
             * @enum {string}
             */
            type: "in" | "out" | "break_start" | "break_end";
            /**
             * Source
             * @constant
             */
            source: "device";
            /** Device Id */
            device_id: string;
            /** Location */
            location: string;
        };
        /** ReadinessGroupOut */
        ReadinessGroupOut: {
            /** Team */
            team: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "ready_with_notes" | "blocked";
            /** Reasons */
            reasons: components["schemas"]["ReadinessReasonOut"][];
        };
        /** ReadinessReasonOut */
        ReadinessReasonOut: {
            /** Employee Id */
            employee_id: string;
            /** Code */
            code: string;
            /** Message */
            message: string;
            /** Blocking */
            blocking: boolean;
            /** Exception Ids */
            exception_ids: string[];
            /** Owner Id */
            owner_id: string | null;
            /** Owner Name */
            owner_name: string | null;
            /** Contact */
            contact: ("worker" | "supervisor" | "hr") | null;
        };
        /** ReadinessWorkerOut */
        ReadinessWorkerOut: {
            /** Team */
            team: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "ready_with_notes" | "blocked";
            /** Reasons */
            reasons: components["schemas"]["ReadinessReasonOut"][];
            /** Employee Id */
            employee_id: string;
            /** Employee Name */
            employee_name: string;
            /** Worked Hours */
            worked_hours: number;
            /** Scheduled Remaining Hours */
            scheduled_remaining_hours: number;
            /** Projected Hours */
            projected_hours: number;
        };
        /** RejectIn */
        RejectIn: {
            /**
             * Reason
             * @description Why the fix is rejected (at least 10 characters, saved in the audit log)
             * @example The worker was on site all day
             */
            reason: string;
        };
        /** RunChecksOut */
        RunChecksOut: {
            /**
             * Ok
             * @default true
             * @constant
             */
            ok: true;
            /** Employee Id */
            employee_id: string;
            /** Week */
            week: string;
            /** Verdict */
            verdict: string;
            /** New Violations */
            new_violations: components["schemas"]["Finding"][];
            /** Resolved */
            resolved: components["schemas"]["Finding"][];
            /** Still Open */
            still_open: components["schemas"]["Finding"][];
            /** Day Worked Hours */
            day_worked_hours?: number | null;
            /** Week Projected Hours */
            week_projected_hours: number;
            /** Weekly Limit Hours */
            weekly_limit_hours: number;
        };
        /** SchedulerCycleOut */
        SchedulerCycleOut: {
            /** Cycle Id */
            cycle_id: number;
            /**
             * Trigger
             * @enum {string}
             */
            trigger: "schedule" | "run_now";
            /**
             * Status
             * @enum {string}
             */
            status: "completed" | "failed";
            /** As Of */
            as_of: string;
            /**
             * Started At
             * @description Real UTC time (operational)
             */
            started_at: string;
            /** Finished At */
            finished_at: string | null;
            /** Duration Ms */
            duration_ms: number | null;
            /**
             * Backlog
             * @description Whether cases detected before the watermark were processed
             */
            backlog: boolean;
            /** Watermark Audit Id */
            watermark_audit_id: number;
            /** Detection */
            detection: ("ok" | "failed") | null;
            /** Detected */
            detected: number;
            /** New */
            new: number;
            /** New Exception Ids */
            new_exception_ids: string[];
            /** Closed Exception Ids */
            closed_exception_ids: string[];
            /** Investigated */
            investigated: components["schemas"]["CycleInvestigationOut"][];
            /** Messages Sent */
            messages_sent: string[];
            /**
             * Skipped Budget
             * @description New cases left for the next cycle
             */
            skipped_budget: string[];
            /** Skipped Message Budget */
            skipped_message_budget: string[];
            /**
             * Skipped Backlog
             * @description Cases detected before the scheduler started that it left alone
             */
            skipped_backlog: number;
            /**
             * Skipped Undone
             * @description Cases whose auto-resolve a person undid: never handled automatically
             * @default 0
             */
            skipped_undone: number;
            /** @description No-reply ladder steps (Phase 13) */
            no_reply?: components["schemas"]["CycleNoReplyOut"];
            /** @description Priya's scheduled daily briefing (Phase 17) */
            briefing?: components["schemas"]["CycleBriefingOut"] | null;
            /** Errors */
            errors: components["schemas"]["CycleErrorOut"][];
        };
        /** SchedulerStatusOut */
        SchedulerStatusOut: {
            /**
             * Enabled Setting
             * @description SCHEDULER_ENABLED at startup
             */
            enabled_setting: boolean;
            /**
             * Running
             * @description The timer thread is running now
             */
            running: boolean;
            /** Cycle In Progress */
            cycle_in_progress: boolean;
            /** Interval Seconds */
            interval_seconds: number;
            /** Investigations Per Cycle */
            investigations_per_cycle: number;
            /** Messages Per Cycle */
            messages_per_cycle: number;
            /** Backlog */
            backlog: boolean;
            /** Next Run At */
            next_run_at: string | null;
            /** Overlaps Skipped */
            overlaps_skipped: number;
            watermark: components["schemas"]["WatermarkOut"] | null;
            last_cycle: components["schemas"]["SchedulerCycleOut"] | null;
            /**
             * As Of
             * Format: date-time
             * @description The demo clock's 'now'
             */
            as_of: string;
            clock: components["schemas"]["DemoClockOut"];
            no_reply: components["schemas"]["NoReplySettingsOut"];
            /** Demo Mode */
            demo_mode: boolean;
            /**
             * Workers
             * @description Workers a simulated punch can be sent for (demo mode only, else empty)
             */
            workers: components["schemas"]["DemoWorkerOut"][];
        };
        /** SeedOut */
        SeedOut: {
            /** Message */
            message: string;
            /** Counts */
            counts: {
                [key: string]: number;
            };
        };
        /** SettingChangeIn */
        SettingChangeIn: {
            /**
             * Value
             * @description The new value: true/false or a JSON number, never a string. Checked against the setting's type and range; a wrong type or range is a plain 422.
             * @example 12
             */
            value: unknown;
            /**
             * Reason
             * @description Why it changes (at least 10 characters, saved in the audit log)
             * @example Workers on the late shift need more time to answer
             */
            reason?: string | null;
            /**
             * Confirm
             * @description Required (true) to turn auto_resolve_enabled on
             * @default false
             */
            confirm: boolean;
        };
        /** SettingChangeOut */
        SettingChangeOut: {
            /** Key */
            key: string;
            before: components["schemas"]["SettingSideOut"];
            after: components["schemas"]["SettingSideOut"];
            setting: components["schemas"]["SettingItemOut"];
        };
        /** SettingHistoryItemOut */
        SettingHistoryItemOut: {
            /** Id */
            id: number;
            /**
             * At
             * Format: date-time
             */
            at: string;
            /**
             * Action
             * @enum {string}
             */
            action: "settings_changed" | "settings_reset";
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Actor Id */
            actor_id: string | null;
            /** Actor Name */
            actor_name: string | null;
            /** Old Value */
            old_value: boolean | number | null;
            /** Old Source */
            old_source: ("default" | "env" | "override") | null;
            /** New Value */
            new_value: boolean | number | null;
            /** New Source */
            new_source: ("default" | "env" | "override") | null;
            /** Old Text */
            old_text: string | null;
            /** New Text */
            new_text: string | null;
            /** Reason */
            reason: string | null;
        };
        /** SettingHistoryOut */
        SettingHistoryOut: {
            /** Items */
            items: components["schemas"]["SettingHistoryItemOut"][];
            /** Next Before Id */
            next_before_id: number | null;
        };
        /** SettingItemOut */
        SettingItemOut: {
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Group */
            group: string;
            /** Help */
            help: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "bool" | "int" | "half";
            /** Value */
            value: boolean | number;
            /** Value Text */
            value_text: string;
            /**
             * Source
             * @enum {string}
             */
            source: "default" | "env" | "override";
            /** Server Value */
            server_value: boolean | number;
            /** Default Value */
            default_value: boolean | number;
            /** Env Var */
            env_var: string;
            /** Editable */
            editable: boolean;
            /** Minimum */
            minimum: number | null;
            /** Maximum */
            maximum: number | null;
            /** Unit */
            unit: string | null;
            /** Range Text */
            range_text: string | null;
            /** Within Range */
            within_range: boolean;
            /** Needs Confirm To Enable */
            needs_confirm_to_enable: boolean;
            /** Locked Note */
            locked_note: string | null;
            last_change: components["schemas"]["SettingHistoryItemOut"] | null;
        };
        /** SettingResetIn */
        SettingResetIn: {
            /**
             * Reason
             * @description Why the override is removed (at least 10 characters, saved in the audit)
             * @example Back to the server value after the demo
             */
            reason?: string | null;
        };
        /** SettingSideOut */
        SettingSideOut: {
            /** Key */
            key: string;
            /** Value */
            value: boolean | number;
            /**
             * Source
             * @enum {string}
             */
            source: "default" | "env" | "override";
        };
        /** SettingsOut */
        SettingsOut: {
            /**
             * Profile
             * @enum {string}
             */
            profile: "local" | "guided" | "locked";
            /** Changes Allowed */
            changes_allowed: boolean;
            /** Locked Reason */
            locked_reason: string | null;
            /** Min Reason Length */
            min_reason_length: number;
            /** Items */
            items: components["schemas"]["SettingItemOut"][];
        };
        /** SupervisorCaseOut */
        SupervisorCaseOut: {
            /** Exception Id */
            exception_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated";
            /** Assigned To */
            assigned_to: string | null;
            employee: components["schemas"]["CardEmployeeOut"];
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Policy Id */
            policy_id: string;
            /** Title */
            title: string;
            /** Summary */
            summary: string;
            /**
             * Severity
             * @enum {string}
             */
            severity: "low" | "medium" | "high";
            /**
             * Kind
             * @enum {string}
             */
            kind: "breach" | "risk";
            /** Details */
            details: {
                [key: string]: unknown;
            };
            policy: components["schemas"]["CardPolicyOut"];
            /** Evidence */
            evidence: {
                [key: string]: unknown;
            }[];
            /** Other Workers Evidence Hidden */
            other_workers_evidence_hidden: number;
            investigation: components["schemas"]["CardInvestigationOut"] | null;
            worker: components["schemas"]["CardWorkerOut"] | null;
            confirmed_time: components["schemas"]["CardConfirmedTimeOut"] | null;
            recheck: components["schemas"]["RunChecksOut"] | null;
            /** Options */
            options: components["schemas"]["CardOptionOut"][];
            /** Applied Fix */
            applied_fix: {
                [key: string]: unknown;
            } | null;
            /** Min Note Length */
            min_note_length: number;
            no_reply?: components["schemas"]["NoReplyOut"] | null;
            /**
             * Can Decide
             * @description True only for the assignee. The team's supervisor may open the card read-only (Phase 14); every decision endpoint still requires the assignee.
             */
            can_decide: boolean;
            /**
             * Trace
             * @description The latest investigation's tool calls: name, ok and a result line built by code (no arguments, raw outputs or prompts)
             */
            trace: components["schemas"]["TraceStepOut"][];
        };
        /** SupervisorQueueItemOut */
        SupervisorQueueItemOut: {
            /** Exception Id */
            exception_id: string;
            /** Employee Id */
            employee_id: string;
            /** Employee Name */
            employee_name: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Policy Id */
            policy_id: string;
            /** Title */
            title: string;
            /** Summary */
            summary: string;
            /**
             * Severity
             * @enum {string}
             */
            severity: "low" | "medium" | "high";
            /**
             * Kind
             * @enum {string}
             */
            kind: "breach" | "risk";
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated";
            /** Waiting Since */
            waiting_since: string | null;
            /**
             * Auto Resolve Undone
             * @description A person undid its auto-resolve; decide it by hand
             * @default false
             */
            auto_resolve_undone: boolean;
            /** @description Set when the worker did not reply in time (Phase 13) */
            no_reply?: components["schemas"]["NoReplyOut"] | null;
        };
        /** SupervisorQueueOut */
        SupervisorQueueOut: {
            /** Count */
            count: number;
            /** Items */
            items: components["schemas"]["SupervisorQueueItemOut"][];
        };
        /** TeamAutoFixItemOut */
        TeamAutoFixItemOut: {
            /** Exception Id */
            exception_id: string;
            /** Employee Id */
            employee_id: string;
            /** Employee Name */
            employee_name: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Policy Id */
            policy_id: string;
            /** Title */
            title: string;
            /** Summary */
            summary: string;
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated";
            auto_fix: components["schemas"]["AutoFixOut"] | null;
        };
        /** TeamAutoFixesOut */
        TeamAutoFixesOut: {
            /** Count */
            count: number;
            /** Items */
            items: components["schemas"]["TeamAutoFixItemOut"][];
        };
        /** ToolCallListOut */
        ToolCallListOut: {
            /** Count */
            count: number;
            /** Items */
            items: components["schemas"]["ToolCallOut"][];
        };
        /** ToolCallOut */
        ToolCallOut: {
            /** Id */
            id: number;
            /** Exception Id */
            exception_id: string;
            /** Step No */
            step_no: number;
            /** Run Id */
            run_id: string | null;
            /** Call No */
            call_no: number | null;
            /** Ok */
            ok: boolean | null;
            /** Duration Ms */
            duration_ms: number | null;
            /** Tool Name */
            tool_name: string;
            /** Input */
            input: {
                [key: string]: unknown;
            };
            /** Output */
            output: {
                [key: string]: unknown;
            } | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** TraceStepOut */
        TraceStepOut: {
            /** Step No */
            step_no: number;
            /** Tool Name */
            tool_name: string;
            /** Ok */
            ok: boolean | null;
            /** Result Summary */
            result_summary: string;
        };
        /** UndoIn */
        UndoIn: {
            /**
             * Reason
             * @description Why the auto-resolve is undone (at least 10 characters, saved in the audit)
             * @example The worker says the second tap was a real re-entry
             */
            reason: string;
        };
        /** UndoOut */
        UndoOut: {
            /**
             * Id
             * @example P1-E001-2026-04-14
             */
            id: string;
            /** Employee Id */
            employee_id: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Policy Id */
            policy_id: string;
            /** Title */
            title: string;
            /** Summary */
            summary: string;
            /**
             * Severity
             * @enum {string}
             */
            severity: "low" | "medium" | "high";
            /**
             * Kind
             * @enum {string}
             */
            kind: "breach" | "risk";
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated";
            /** Auto Resolved */
            auto_resolved: boolean;
            /**
             * Auto Resolve Undone At
             * @description Set when a person undid the auto-resolve (Phase 12)
             */
            auto_resolve_undone_at?: string | null;
            /** Auto Resolve Undone By */
            auto_resolve_undone_by?: string | null;
            /**
             * No Reply Stage
             * @description No-reply ladder (Phase 13): 0 none, 1 reminder sent, 2 supervisor brought in, 3 sent to payroll
             * @default 0
             */
            no_reply_stage: number;
            /** No Reply Wait Since */
            no_reply_wait_since?: string | null;
            /** No Reply Reminded At */
            no_reply_reminded_at?: string | null;
            /** No Reply Supervisor At */
            no_reply_supervisor_at?: string | null;
            /** No Reply Admin At */
            no_reply_admin_at?: string | null;
            /** No Reply Late Reply At */
            no_reply_late_reply_at?: string | null;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Evidence */
            evidence: {
                [key: string]: unknown;
            }[];
            /** Fix Options */
            fix_options: components["schemas"]["FixOptionOut"][];
            /** Proposed Fix */
            proposed_fix: {
                [key: string]: unknown;
            } | null;
            worker_recheck?: components["schemas"]["WorkerRecheckOut"] | null;
            /** Applied Fix */
            applied_fix: {
                [key: string]: unknown;
            } | null;
            /**
             * Assigned To
             * @description Whose turn it is to act
             */
            assigned_to: string | null;
            /** Waiting Since */
            waiting_since: string | null;
            /**
             * Last Detected At
             * Format: date-time
             */
            last_detected_at: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Audit Trail */
            audit_trail: components["schemas"]["AuditEntryOut"][];
            investigation_case?: components["schemas"]["InvestigationCase"] | null;
            /**
             * Restored
             * @description Rows put back to their 'before' values
             */
            restored: {
                [key: string]: unknown;
            }[];
            detection: components["schemas"]["PostFixDetectionOut"];
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
        /** WatermarkOut */
        WatermarkOut: {
            /** Audit Id */
            audit_id: number;
            /**
             * Set By
             * @enum {string}
             */
            set_by: "scheduler_start" | "demo_reset" | "first_cycle";
            /** Set At */
            set_at: string;
        };
        /** WorkerAnswerOut */
        WorkerAnswerOut: {
            /**
             * Confirmed
             * @description Yes (true), No (false), or no choice yet
             */
            confirmed: boolean | null;
            /**
             * Text
             * @description The worker's own words, if any
             */
            text?: string | null;
            /**
             * Time
             * @description The time the worker confirmed (HH:MM)
             */
            time?: string | null;
            /** Replied At */
            replied_at?: string | null;
        };
        /** WorkerHistoryItemOut */
        WorkerHistoryItemOut: {
            /** Exception Id */
            exception_id: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Questions */
            questions: components["schemas"]["WorkerHistoryQuestionOut"][];
            outcome: components["schemas"]["WorkerOutcomeOut"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** WorkerHistoryOut */
        WorkerHistoryOut: {
            /** Items */
            items: components["schemas"]["WorkerHistoryItemOut"][];
        };
        /** WorkerHistoryQuestionOut */
        WorkerHistoryQuestionOut: {
            /**
             * Asked At
             * Format: date-time
             */
            asked_at: string;
            /** Message */
            message: string;
            /** Reminded At */
            reminded_at?: string | null;
            answer?: components["schemas"]["WorkerAnswerOut"] | null;
        };
        /** WorkerInboxOut */
        WorkerInboxOut: {
            /** Items */
            items: components["schemas"]["WorkerMessageOut"][];
            /**
             * Notices
             * @description Plain notes about cases the worker can no longer answer
             */
            notices?: components["schemas"]["WorkerNoticeOut"][];
        };
        /** WorkerMessageOut */
        WorkerMessageOut: {
            /** Exception Id */
            exception_id: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Message */
            message: string;
            /** Reply Prompt */
            reply_prompt: string;
            /** Needs Actual Time */
            needs_actual_time: boolean;
            time_review?: components["schemas"]["WorkerTimeReviewOut"] | null;
            reminder?: components["schemas"]["WorkerReminderOut"] | null;
            /**
             * Status Note
             * @description Set when the supervisor now reviews it (still answerable)
             */
            status_note?: string | null;
        };
        /** WorkerNoticeOut */
        WorkerNoticeOut: {
            /** Exception Id */
            exception_id: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "decided_without_reply" | "with_payroll";
            /** Title */
            title: string;
            /** Text */
            text: string;
            /** Reason */
            reason?: string | null;
            /** At */
            at?: string | null;
        };
        /** WorkerOutcomeOut */
        WorkerOutcomeOut: {
            /**
             * State
             * @enum {string}
             */
            state: "waiting_for_you" | "with_supervisor" | "with_payroll" | "decided_without_reply" | "decided" | "fixed" | "closed_no_change";
            /**
             * Text
             * @description Built by code, in plain words
             */
            text: string;
            /**
             * Reason
             * @description Only for a decision taken without the worker's reply
             */
            reason?: string | null;
        };
        /** WorkerRecheckOut */
        WorkerRecheckOut: {
            /** Timestamp */
            timestamp: string;
            /**
             * Source
             * @enum {string}
             */
            source: "yes" | "llm" | "manual";
            /** Proposed Fix */
            proposed_fix: {
                [key: string]: unknown;
            };
            result: components["schemas"]["RunChecksOut"];
            /** Impact Note */
            impact_note: string;
            /**
             * Approximate
             * @description The worker confirmed an approximate time (e.g. '7:30ish')
             * @default false
             */
            approximate: boolean;
        };
        /** WorkerReminderOut */
        WorkerReminderOut: {
            /**
             * Text
             * @description Deterministic template, never the LLM
             */
            text: string;
            /**
             * Sent At
             * Format: date-time
             */
            sent_at: string;
        };
        /** WorkerReplyIn */
        WorkerReplyIn: {
            /**
             * Confirmed
             * @description Yes/No: did it happen as described?
             */
            confirmed: boolean;
            /**
             * Text
             * @example left around 7:30ish
             */
            text?: string | null;
        };
        /** WorkerReplyOut */
        WorkerReplyOut: {
            /** Exception Id */
            exception_id: string;
            /** Confirmed */
            confirmed: boolean;
            /** Needs Actual Time */
            needs_actual_time: boolean;
            time_review?: components["schemas"]["WorkerTimeReviewOut"] | null;
        };
        /** WorkerTimeIn */
        WorkerTimeIn: {
            /** Time */
            time: string;
            /** Actual Date */
            actual_date?: string | null;
        };
        /** WorkerTimeReviewOut */
        WorkerTimeReviewOut: {
            /**
             * Stage
             * @enum {string}
             */
            stage: "candidate" | "manual" | "confirmed";
            /** Timestamp */
            timestamp?: string | null;
            /** Impact Note */
            impact_note?: string | null;
            /**
             * Approximate
             * @default false
             */
            approximate: boolean;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    health_api_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthOut"];
                };
            };
        };
    };
    seed_api_seed_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SeedOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    run_detection_api_detection_run_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetectionRunOut"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_exceptions_api_exceptions_get: {
        parameters: {
            query?: {
                status?: ("open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated") | null;
                employee_id?: string | null;
                policy_id?: string | null;
                assigned_to?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExceptionListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_exception_api_exceptions__exception_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExceptionDetailOut"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_investigation_api_exceptions__exception_id__investigate_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InvestigationJobOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    poll_investigation_api_exceptions__exception_id__investigate__job_id__get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InvestigationJobOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    approve_api_exceptions__exception_id__approve_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApproveIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApproveOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    edit_api_exceptions__exception_id__edit_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EditIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApproveOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    reject_api_exceptions__exception_id__reject_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RejectIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExceptionDetailOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    escalate_api_exceptions__exception_id__escalate_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EscalateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExceptionDetailOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    undo_api_exceptions__exception_id__undo_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UndoIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UndoOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    ask_worker_api_exceptions__exception_id__ask_worker_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AskWorkerIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExceptionDetailOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    worker_reply_api_exceptions__exception_id__worker_reply_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkerReplyIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkerReplyOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    worker_confirm_time_api_exceptions__exception_id__worker_confirm_time_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkerReplyOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    worker_manual_time_api_exceptions__exception_id__worker_manual_time_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkerTimeIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkerReplyOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    worker_messages_api_worker_messages_get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkerInboxOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    worker_history_api_worker_history_get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkerHistoryOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    worker_ask_api_worker_ask_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AskIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AskResultOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    worker_ask_history_api_worker_ask_history_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AskHistoryOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    admin_worker_questions_api_admin_worker_questions_get: {
        parameters: {
            query?: {
                employee_id?: string | null;
                limit?: number;
                offset?: number;
            };
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminQuestionsOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_briefing_api_briefing_get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BriefingOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    refresh_briefing_api_briefing_refresh_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BriefingOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    supervisor_queue_api_supervisor_queue_get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupervisorQueueOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    supervisor_case_api_supervisor_cases__exception_id__get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupervisorCaseOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    supervisor_auto_resolved_api_supervisor_auto_resolved_get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TeamAutoFixesOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    auto_resolve_metric_api_admin_metrics_auto_resolve_get: {
        parameters: {
            query?: {
                date_from?: string | null;
                date_to?: string | null;
            };
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AutoResolveMetricOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    operations_dashboard_api_dashboard_get: {
        parameters: {
            query?: {
                date_from?: string | null;
                date_to?: string | null;
            };
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    payroll_readiness_api_payroll_get: {
        parameters: {
            query?: {
                week_start?: string | null;
            };
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PayrollReadinessOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    payroll_sign_off_api_payroll__week_start__sign_off_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                week_start: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PayrollSignoffIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PayrollReadinessOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    payroll_reopen_api_payroll__week_start__reopen_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                week_start: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PayrollReopenIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PayrollReadinessOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    admin_exceptions_api_admin_exceptions_get: {
        parameters: {
            query?: {
                status?: ("open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated") | null;
                policy_id?: string | null;
                team?: string | null;
                employee_id?: string | null;
                severity?: ("low" | "medium" | "high") | null;
                q?: string | null;
                /** @description Cases the no-reply ladder touched, at one stage, or before the reminder */
                no_reply?: ("any" | "reminded" | "supervisor" | "payroll_admin" | "waiting") | null;
                active_only?: boolean;
                auto_resolved?: boolean | null;
                supervisor_id?: string | null;
                date_from?: string | null;
                date_to?: string | null;
                sort?: "severity" | "date" | "employee" | "updated";
                limit?: number;
                offset?: number;
            };
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminOverviewOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    admin_exception_api_admin_exceptions__exception_id__get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                exception_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminCaseOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_runtime_settings_api_settings_get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingsOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_settings_history_api_settings_history_get: {
        parameters: {
            query?: {
                key?: string | null;
                before_id?: number | null;
                limit?: number;
            };
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingHistoryOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    put_setting_api_settings__key__put: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                /** @description Setting key */
                key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SettingChangeIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingChangeOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    reset_setting_api_settings__key__reset_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path: {
                /** @description Setting key */
                key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SettingResetIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingChangeOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    activity_feed_api_activity_get: {
        parameters: {
            query?: {
                /** @description audit_log actor */
                actor_type?: ("system" | "agent" | "worker" | "supervisor" | "admin" | "device") | null;
                /** @description autonomous = system, agent, device; human = people */
                mode?: "all" | "autonomous" | "human";
                policy_id?: string | null;
                employee_id?: string | null;
                exception_id?: string | null;
                /** @description Workflow date, inclusive */
                date_from?: string | null;
                /** @description Workflow date, inclusive */
                date_to?: string | null;
                before_id?: number | null;
                limit?: number;
            };
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActivityFeedOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    activity_summary_api_activity_summary_get: {
        parameters: {
            query?: {
                policy_id?: string | null;
                employee_id?: string | null;
                exception_id?: string | null;
                date_from?: string | null;
                date_to?: string | null;
            };
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActivitySummaryOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    autonomy_table_api_autonomy_get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AutonomyTableOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    audit_log_api_audit_log_get: {
        parameters: {
            query?: {
                exception_id?: string | null;
                actor?: ("system" | "agent" | "worker" | "supervisor" | "admin" | "device") | null;
                actor_id?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    tool_calls_api_tool_calls_get: {
        parameters: {
            query?: {
                exception_id?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ToolCallListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    receive_punch_api_punches_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Device-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PunchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PunchAcceptedOut"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    scheduler_status_api_admin_scheduler_get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SchedulerStatusOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    scheduler_run_now_api_admin_scheduler_run_now_post: {
        parameters: {
            query?: {
                model_free?: boolean;
            };
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SchedulerCycleOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    scheduler_start_api_admin_scheduler_start_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SchedulerStatusOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    scheduler_stop_api_admin_scheduler_stop_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SchedulerStatusOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    demo_reset_api_admin_demo_reset_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DemoResetOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    demo_punch_api_admin_demo_punch_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DemoPunchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PunchAcceptedOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    demo_clock_get_api_admin_demo_clock_get: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DemoClockOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    demo_clock_move_api_admin_demo_clock_post: {
        parameters: {
            query?: never;
            header: {
                /** @description Employee ID of the person acting (no login yet), e.g. E101 for Ravi */
                "X-Actor-Id": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DemoClockIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DemoClockOut"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
}
