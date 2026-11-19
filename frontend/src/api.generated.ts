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
    "/api/supervisor/queue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Cases waiting for the caller's decision
         * @description A supervisor sees their own team's cases assigned to them that are awaiting_supervisor, or open with an investigation routed to the supervisor, plus escalated cases assigned to them. The payroll admin sees escalated cases assigned to them. Cases still waiting for the worker's actual time never appear. Workers get 403. Sorted by severity (high first), then date, then ID.
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
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
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
            actor: "system" | "agent" | "worker" | "supervisor" | "admin";
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
            actor: "system" | "agent" | "worker" | "supervisor" | "admin";
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
        /** SeedOut */
        SeedOut: {
            /** Message */
            message: string;
            /** Counts */
            counts: {
                [key: string]: number;
            };
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
        };
        /** SupervisorQueueOut */
        SupervisorQueueOut: {
            /** Count */
            count: number;
            /** Items */
            items: components["schemas"]["SupervisorQueueItemOut"][];
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
        /** WorkerInboxOut */
        WorkerInboxOut: {
            /** Items */
            items: components["schemas"]["WorkerMessageOut"][];
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
    admin_exceptions_api_admin_exceptions_get: {
        parameters: {
            query?: {
                status?: ("open" | "awaiting_worker" | "awaiting_supervisor" | "resolved" | "rejected" | "escalated") | null;
                policy_id?: string | null;
                team?: string | null;
                employee_id?: string | null;
                severity?: ("low" | "medium" | "high") | null;
                q?: string | null;
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
    audit_log_api_audit_log_get: {
        parameters: {
            query?: {
                exception_id?: string | null;
                actor?: ("system" | "agent" | "worker" | "supervisor" | "admin") | null;
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
}
