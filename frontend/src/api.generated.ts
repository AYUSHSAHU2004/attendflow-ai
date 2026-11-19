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
        /** Approve a fix option: applies it and resolves the exception (one transaction) */
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
             * @example The worker was on site
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
