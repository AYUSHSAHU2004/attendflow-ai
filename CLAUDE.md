# CLAUDE.md: AttendFlow AI

You are the senior engineer building **AttendFlow AI** for the AI Innovation Challenge
(Problem 5: Time & Attendance). The user is a student; work in phases, one phase prompt
at a time. Progress and history live in [docs/PROGRESS.md](docs/PROGRESS.md).

## Product

An AI agent that detects timecard exceptions (missed punches, overtime risks, schedule
conflicts, policy breaches, leave conflicts), investigates them with tools, proposes
policy-compliant fixes, contacts the worker, and sends the case to a supervisor for
approval. It does **not** calculate payroll or salaries. It only cleans attendance data
before payroll.

## Users

- **Priya Sharma** (E201), payroll admin: sees all exceptions, audit log, payroll readiness.
- **Ravi Kumar** (E101), shift supervisor (Inbound team): approves, edits or rejects fixes
  for his team. **Sunita Rao** (E102) supervises the Outbound team.
- **Amit Verma** (E001), warehouse worker: confirms what really happened (Yes/No + free text).

## Core design rule: "Code decides, the LLM talks"

- A deterministic rule engine (plain code, limits read from `data/policy.json`) finds every
  exception, calculates hours, picks the policy ID and builds fix options. No LLM involved.
- The LLM only: (1) investigates by calling tools, (2) explains in plain language,
  (3) writes messages to workers, (4) extracts structured data from free text like
  "left around 7:30ish", (5) writes summaries.
- The LLM can never write to timecards. Fixes are applied by code only after human
  approval. The only exceptions are low-risk auto-resolve types (P2 duplicate punch, P7 late
  arrival within grace). They are configurable in `policy.json` and always audit-logged.
- Every LLM output is validated with Pydantic. On invalid output, retry once, then fall back
  to a template or a manual form. If the LLM is down, the app must still work.

## Tech stack (ask the user before changing)

React + TypeScript frontend, Python FastAPI backend, PostgreSQL, Pydantic, pytest, Docker.
The LLM must be open-source or open-weight, served via Groq, Together or Ollama. Check and
note the model licence in [docs/LLM_LICENCE.md](docs/LLM_LICENCE.md).

## Grading (optimise for this)

Product value 25%, harness engineering 25% (validation, guardrails, fallbacks, human
oversight), LLM implementation 20% (grounding, prompt design), engineering quality 15%
(tests, API design, observability, docs), demo 15%. Deliverables: GitHub repo with README
and CI, 10-minute demo video, 5 slides.

## Working rules (every phase)

1. BEFORE writing any code, list every input, decision or missing detail needed from the
   user as a short numbered list of questions, each with a recommended default. Then STOP
   and wait. Build only after the user replies.
2. Build in small steps. Write unit tests as you go.
3. Never commit secrets. Use `.env` (git-ignored) and `.env.example`.
4. Shift times are stored as plain local times. Never depend on server timezone.
5. At the end of each phase: run the tests, tell the user how to run and verify the phase
   using its "Done when" checklist, and append a short summary to `docs/PROGRESS.md`
   (what was built, decisions made, what is next).
6. Keep explanations short and plain. Explain any non-obvious decision in one or two lines.
7. The user commits and pushes themselves. Tell them what to commit; don't commit unasked.

## Phase plan

Done: 0 Setup + data + policy + LLM test; 1 Rule engine P1-P7, P15; 2 Rules P8-P14, P16, P17;
3 Backend + DB + API; 4 Read-only tools + fix options for P3/P4/P6/P7; 5 LLM client + agent loop; 6 structured investigations and jobs; 7 worker messages and inbox; 8 worker clock-out extraction and re-check; 9 supervisor approval screen; 10 Priya's list +
end-to-end tests (**prototype complete**); 11 mock punch API + scheduler; 12 auto-resolve + undo +
"resolved without a human" metric; 13 no-reply escalation ladder + demo clock; 14 Activity
Center + Autonomy Table (generated, anti-drift tests).

**Prototype (3-10)**
3. Backend + DB + API
4. Read-only tools + fix options for P3/P4/P7
5. LLM client + agent loop
6. InvestigationCase schema + fallback + `/investigate`
7. Worker message + Amit page
8. Free-text extraction + re-check
9. Ravi's approval
10. Priya's plain list + integration test (**prototype done**)

**Full product (11-24)**
11. Mock punch API + scheduler
12. Auto-resolve + undo
13. No-reply escalation
14. Activity Center + autonomy table
15. Role switcher + Priya dashboard
16. Payroll readiness
17. Briefing + Amit mobile + summary
18. Settings backend
19. Admin UI
20. Employee Q&A
21. Analytics
22. Deployment
23. Tests + evaluation
24. Delivery

**Next: Phase 15.**

**Carry-over notes**
- Phase 5 Groq bug: `run_checks` advertised Pydantic's RFC 3339 `date-time` format for
  timezone-free local timestamps. Groq rejected minute-precision values with HTTP 400.
  The schema now advertises the app's local time patterns; the registry tests check
  every tool schema recursively for unsupported formats and schema references.
- Phase 15 (role switcher): replace `frontend/src/actors.ts` (the only place that names
  the acting user, including the dev-only `?as=` override). `/activity` acts as Priya
  (`activityActor`); a supervisor's team-only view needs `?as=E101` in dev until then, and
  the `/supervisor` "Team activity" link adds it in dev builds only.
- Any phase that adds an audit action: add its row to `activity/autonomy.py` first (tests
  fail otherwise), then `python -m uv run attendflow-autonomy --write-readme`.
- **Phase 22 checklist (deployment):**
  - `POST /api/seed` wipes every table. Disable it (`ATTENDFLOW_ENABLE_SEED=false`) or
    protect it.
  - Review or remove the `/dev` page and its fixed demo actors.
  - The `?as=E102` reviewer override in `actors.ts` works only in dev builds
    (`import.meta.env.DEV`); a test checks this. Confirm it is absent from the deployed
    bundle (`grep URLSearchParams frontend/dist/assets/*.js` finds nothing).
  - `X-Actor-Id` is not authentication. Add real login before going public.
  - `GET /api/exceptions`, `/api/audit-log` and `/api/tool-calls` have no role check (used
    by `/dev`). Restrict them to the payroll admin or remove them with `/dev`.
  - Phase 11: set `ATTENDFLOW_DEMO_MODE=false`. That removes `POST /api/admin/demo/reset`
    (wipes every table) and `/api/admin/demo/punch`, and hides the Simulate punch panel.
  - Phase 11: the worker inbox override `?as=E004` (`workerFor` in `actors.ts`) is dev-only
    like the reviewer one; a test checks it. Confirm it is absent from the bundle (same
    `URLSearchParams` grep; also no `Neha` string).
  - Phase 11: set a long random `DEVICE_API_KEY` (or leave it unset to disable
    `POST /api/punches`), and set `ATTENDFLOW_CORS_ORIGINS` to the real frontend origin.
  - Phase 11: the scheduler runs in the API process with an in-process lock. Run one API
    process (or move the lock to a Postgres advisory lock) before scaling out.
  - Phase 11: `scheduler_cycle` rows and `/api/admin/scheduler` expose case IDs only, not
    LLM text. Phase 14 kept it so (the feed hides `scheduler_cycle` rows).
  - Phase 12: review the `AUTO_RESOLVE_ENABLED` default (true) and which policies have
    `"auto_resolve": true` in `policy.json` (code allows only P2 and P7) before deploy.
  - Phase 12: review the metric definition (X = auto-resolved and not undone; Y = all
    minus `closed_by_data_change`) before showing it to real users.
  - Phase 13: with demo mode off the clock stays fixed at `ATTENDFLOW_AS_OF` and **no
    no-reply timeout ever fires**. Decide whether the deployed app runs in demo mode or
    gets a real wall clock (a new `Clock` with `now()` = local time and its own data
    cut-off rule). `/api/admin/demo/clock` must not exist on a real server.
  - Phase 13: review the N/M/K defaults (`NO_REPLY_REMINDER_HOURS` 8,
    `NO_REPLY_SUPERVISOR_HOURS` 24, `NO_REPLY_ADMIN_HOURS` 24; calendar hours, not shift
    hours) and the `NO_REPLY_ESCALATION_ENABLED` switch before deploy.
  - Phase 13: the worker inbox shows the supervisor's reason for a decision made without
    the worker's reply. Tell supervisors and payroll that this text is shown to the worker.
  - Phase 14: `/api/activity`, `/api/activity/summary` and `/api/autonomy` trust
    `X-Actor-Id` like every endpoint (real login first). The feed shows a person's typed
    reasons and a worker's free-text "No" reply to payroll and the team's supervisor.
  - Phase 14: the supervisor case card now opens read-only for any case of the
    supervisor's own team (`can_decide` false); decisions still need the assignee.

## Decisions so far (do not re-ask)

**Environment**
- Project path: the repo root (the path differs per machine). Keep it out of cloud-synced
  folders such as OneDrive to avoid sync and lock problems. GitHub: https://github.com/AYUSHSAHU2004/attendflow-ai (branch `main`).
- Python **3.12** managed with **uv**; dependencies are pinned in `uv.lock`. The machine's
  default Python is 3.14, so always go through uv. `uv` is not on PATH here, so use
  `python -m uv ...`.
- Windows + Git Bash/PowerShell. Scripts that print LLM text must reconfigure stdout to
  UTF-8 (the cp1252 console crashes on Unicode punctuation).

**LLM**
- Model: **`openai/gpt-oss-120b`** (open-weight, **Apache 2.0**) on Groq, via the
  OpenAI-compatible endpoint `https://api.groq.com/openai/v1`.
- It replaced the original plan (Llama 3.3 70B) because Groq retired that model
  (checked 2026-11-19). The user chose gpt-oss-120b over `qwen/qwen3.8-27b`.
- Configured by `.env`: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_TIMEOUT_SECONDS`.
  Switching provider is only a `.env` change.

**Demo data**
- Demo week: **Mon 13 to Sun 19 Apr 2026**. Holiday: **Tue 14 Apr 2026, Ambedkar Jayanti**
  (national). Most staff are off that day. Amit and Meena are on the holiday-duty roster.
- As-of ("now") time: **Thu 16 Apr 2026, 08:00** (`ATTENDFLOW_AS_OF`). Punches after it are
  ignored. Schedule rows after it are the forecast, so Meena's overtime is a *risk*, not a
  breach yet.
- The work week runs Monday to Sunday (P5, P16). The standard day shift is 09:00-18:00
  with a 1 h lunch, so 8 h worked.
- 10 workers in 2 teams (Inbound/Ravi: Amit, Meena, Neha, Sana, Arjun. Outbound/Sunita:
  Ramesh, Karan, Dev, Farah, Pooja), plus Ravi, Sunita and Priya. Arjun and Pooja are clean
  controls.
- Leave: sick 12, casual 12, earned 15 per calendar year. The balance is never stored; it
  is computed as `total_per_year - used`. Dev's sick leave is 12 total, 11 used, 3 days
  pending with no certificate.
- The CSVs are produced by the deterministic generator `attendflow-generate-data` (seed 42).
  Never hand-edit a CSV; change the generator. A test enforces this.
- Expected side-effect flags (documented, intended):
  - **Meena**: P5 risk (36 h worked + 12 h scheduled = 48 h), plus **P3** on Mon, Tue and
    Wed (12 h days) and **P14** on Tue (holiday duty). No P6 (11.5 h rest).
  - **Sana**: P2 (Mon duplicate, auto-resolve), plus Tue holiday work gives **P14 and P8**
    (not scheduled).
  - **Amit**: P1 on Tue, plus **P14** (the missed clock-out is on the holiday, while on
    holiday duty).
  - Farah gets P13 (not P9). Dev gets P11 and P12 (not P10). Ramesh's night shifts must
    trigger nothing (P15 attribution).
- **P6, P16 and P17 have no planted case**; they are tested with synthetic fixtures. Add a
  demo case (e.g. for P17) only if the user asks. The full demo run gives 17 exceptions.
- Full answer key: [docs/PLANTED_CASES.md](docs/PLANTED_CASES.md).

**Rule engine (Phase 1)**
- Phase 1 covered P1-P7 + P15. Phase 1 demo tests run with `policies=P1-P7`.
- Engine params added to policy.json (and mirrored in policy.md): P1 `open_shift_grace_hours` 4;
  P5 `planned_break_after_hours` 6 + `planned_break_minutes` 60 (09:00-18:00 = 8 h planned,
  09:00-15:00 = 6 h); P15 `match_before_start_hours` 4, `match_after_end_hours` 6,
  `max_shift_hours` 16.
- Limits are exceeded only when strictly over (9 h, 5 h, 40 h, 10 min are fine; P6 flags < 11 h).
- A past shift with a missing punch counts at its scheduled hours for P5; skipped by P3/P4.
- P5 and P6 have `kind` breach (already happened) or risk (forecast from schedule).
- P7 covers late arrival and early leave. Late within grace -> auto-resolved record; early
  leave within grace -> nothing (keeps Amit's 2-5 min early exits clean).
- fix_options are filled for P1 (clock-in/out = scheduled start/end) and P5 (approve overtime,
  or cut the exact hours from the latest upcoming shifts). P3, P4 and P7: still empty.

**Rule engine (Phase 2)**
- P8-P14, P16 and new **P17 "Possible punch conflict, needs review"** (never "fraud"; a test
  checks this). P17 has 3 checks: 2+ workers on one terminal at the same second (device
  punches only); one worker at 2 *sites* < 60 min apart (`sites` map location -> site in
  policy.json); app punch from a location not in `approved_app_locations`.
- Generator: each worker has a fixed seconds offset (0 to -29 s) on all punches, so no
  same-second clashes, unchanged durations, unchanged punch IDs. Displayed times are rounded
  to the minute.
- Check order: leave is applied to the schedule when RuleContext is built (before any
  check). Approved and pending full days count as 0 h, half days as -4 h. Used by P5, P6 and
  P16 forecasts. Shift grouping, P8 and P1-P4/P7 still use the full schedule.
- P9 and P13 cover approved **and pending** leave; rejected leave is ignored. P10 skips any
  leave of any status and fires after scheduled end + P1 grace. P7 skips leave days.
- P11: applied = pending days (half = 0.5) vs total - used (approved is already in used).
  Paid days go to the earliest dates. Fixes: split paid/unpaid, move to another type with
  room (casual first), reject extra days.
- P12: sort first; holidays and unscheduled days don't break a run; a scheduled working day
  or a worked day does. Any certificate in the run is enough.
- P13: 4 h +/- `tolerance_hours` 1. Over 5 h = worked full day; under 3 h (incl. none,
  after the day) = working half missing.
- P14: national and company holidays only. Severity **low** when scheduled (holiday duty),
  **medium** when unscheduled (with P8). Comp-off 0.5 day if <= 4 h, else 1. `depends_on`
  lists P1/P8 to fix first.
- P16: breach from worked days, risk from the leave-adjusted upcoming schedule.
- Exception `evidence` can hold punches, leave, balance, schedule and holiday rows. Rows dump
  to JSON in their CSV formats (so JSON loads back).

**Backend (Phase 3)**
- PostgreSQL 16 in Docker (`docker compose up -d db`) on host port **5433**: this machine
  already runs a local PostgreSQL 18 service on 5432. Dev DB `attendflow`, test DB
  `attendflow_test` (created by `docker/initdb`). SQLAlchemy 2 (sync) + psycopg 3 + Alembic.
- API tests run on real Postgres; skipped with a message if unreachable, except in CI
  (`REQUIRE_DB=1`). The test DB schema is built by the real migrations.
- Tests drop and rebuild their database's schema, so `tests/conftest.py` refuses (fails,
  never skips) any database whose name does not end in `_test`, checked on the URL and on
  the server.
- Detection reads the **DB**, not the CSVs. `POST /api/seed` = full demo reset.
  Upsert by `exception_id`: open rows refreshed, in-progress/resolved/rejected untouched,
  open rows no longer found -> `resolved` by system ("no_longer_detected").
- Auto-resolve (P2): stored `resolved` + `auto_resolved=true`, duplicate tap voided in the
  DB in the same transaction, audit rows `detected` + `auto_resolve` (actor system).
- Status flow (`cases/transitions.py`): open -> awaiting_worker | awaiting_supervisor |
  resolved | escalated; awaiting_worker -> awaiting_supervisor | escalated;
  awaiting_supervisor -> resolved | awaiting_worker | escalated; escalated ->
  awaiting_supervisor | resolved | rejected. resolved/rejected are final. 409 otherwise.
- **Reject:** a supervisor's reject moves the case to `escalated`, assigned to the payroll
  admin (E201), reason in the audit log. Only the assignee's reject of an escalated case
  is final (`rejected`).
- **Permissions:** `X-Actor-Id` header (no login yet). Only the person in `assigned_to`
  may approve/edit/reject/ask-worker; `assigned_to` always names whose turn it is
  (supervisor -> worker while awaiting_worker -> supervisor; E201 after an escalation).
- Approve = pick an `option_id`; edit = approve with changed params (merged, validated by
  a Pydantic model per action in `fixes/params.py`). `edit_punches` needs `changes`.
- `fixes/apply.py` is the only writer of timecards/schedule/leave (plus the seed); a test
  enforces it. Fix + exception update + audit row in one transaction. Punches are never
  deleted: corrections void the old row and add `source="correction"`. Decision-only
  actions (overtime, holiday pay, comp-off, ...) change no data, only `applied_fix`.
- All `created_at`/`updated_at`/`waiting_since` come from `clock.FixedClock(as_of)`;
  rows are ordered by id. Log timestamps are real UTC (they are operational).
- Errors: always `{"error": {"code", "message", "details"}}`. Logs: one JSON line per
  event with request_id (`LOG_FORMAT=text` for local reading).

**Fix options + tools (Phase 4)**
- Every FixOption has `description`, `decision_only`, `policy_id` and
  `requires_worker_confirmation`. `decision_only` and the default description come from
  `ACTION_INFO` in `engine/models.py` (a test checks it against `fixes/params.py`).
- P3: `approve_overtime` (decision) + `correct_clock_out` (void + new punch; prefilled at
  the 9 h limit, e.g. Meena 16:29:47; worker must confirm). P4: `record_break` (`add_break`,
  30 min from the shift middle, e.g. Neha 12:00-12:30; worker must confirm) +
  `record_missed_break` (decision, `follow_up` required). P6: `record_short_rest` (decision,
  `reason` required) + `move_next_shift_later` (`move_shift`, only for an upcoming
  scheduled shift: previous end + 11 h, rounded up to the minute, same length, never
  onto another date). P7 (late and early): `accept_reason` (`reason` required) +
  `record_as_late` / `record_as_early_leave` (`record_lateness`). Both decision-only;
  policy.md does not allow turning missed minutes into leave, so there is no such option.
- policy.md P7 got one sentence (user-approved): "Early leave beyond grace is handled the
  same way."
- Required notes (`REQUIRED_NOTE` in params.py): an empty note is filled from the approve
  `reason`; with neither, approve is 422 `invalid_params`.
- `requires_worker_confirmation`: approve is 409 `worker_not_confirmed` unless the latest
  `worker_reply` on the case said Yes.
- Detection adds options (only) to non-final cases stored with none; audit `options_added`.
- Tools (`backend/attendflow/tools/`): get_schedule, get_leave, get_leave_balance,
  get_punches, get_policy, run_checks. Results are `{"ok": true, ...}` or
  `{"ok": false, "error": {code, message, hint}}`, never exceptions. Inputs are IDs + ISO
  dates only. Output budgets (tested): 1,000 chars; get_policy 2,000; run_checks 1,200.
- Read-only: tools never get a session. `ToolRunner.for_database` loads a Dataset in a
  `SET TRANSACTION READ ONLY` session (plus a flush guard) and always rolls back; tests
  snapshot every table around every tool and forbid writer imports in `tools/`.
- run_checks: the change uses the fix-option `{action, params}` shape, is applied to an
  in-memory copy (`tools/simulate.py`, same guards as apply.py), the full engine re-runs,
  and results are filtered to that worker's Mon-Sun week: `new_violations`, `resolved`,
  `still_open`, day and week hours. A parity test checks it against the real writer.

**Investigation loop (Phase 5)**
- `agent/loop.py` reads a stored exception in a read-only transaction, calls the model
  with `openai_tools()`, and sends each ToolRunner result back with its tool call ID.
  `AGENT_MAX_STEPS` defaults to 5, with one model turn and its tool calls per step.
- The client validates native assistant messages and retries HTTP 429/5xx twice with
  1 s and 2 s backoff, honoring `Retry-After` up to 60 s. `LLM_REASONING_EFFORT`
  defaults to `low`; use `off` to omit the parameter.
- `AgentRun` contains the steps, final text, total duration, run ID, and stop reason
  (`final`, `max_steps`, or `llm_error`). `missing_required_tools` lists evidence reads
  still needed for this employee/date and policy. The loop selects each required read
  in turn and blocks `run_checks` until all four have succeeded. Phase 6 can reject an
  incomplete run even if the model returned a final answer. The journal commits each call in a
  separate session and records start and end audit events as actor `agent`.
  Migration `0002_agent_tool_calls` adds run ID, per-step call index, outcome and timing.
  The investigation leaves source data and case state untouched.

**Structured investigations (Phase 6)**
- `POST /api/exceptions/{id}/investigate` takes `X-Actor-Id` for the assigned
  supervisor or a payroll admin. It returns a 202 and a polling URL in `Location`.
  Repeated requests share the active job. `GET /api/exceptions/{id}` shows the latest
  case. Investigations keep the exception status and source data unchanged.
- The code reads and journals schedule, punches, leave and the cited policy before
  contacting the model. The draft provides a short narrative, a verbatim policy quote,
  source-linked evidence, a stored option or null, and confidence. Code owns the next
  contact, next action, fallback flag, tool count, duration, and persisted simulation.
- Validation checks the exact stored option and normalized parameters, the policy quote,
  numbers and times against each evidence source, and human-approval contradictions.
  Simulatable options require a matching successful `run_checks` row from the same
  run, whose output is copied into the case. Decision-only options have no simulation.
- The first live Amit P1 investigation completed simulation, then failed on the final
  model call. Its job and audit retained only `llm_error`, so the exact cause is unknown.
  The failure predates JSON mode. The final request now uses a fresh system/user
  conversation in JSON mode, with the recorded simulation as evidence and no tool
  definitions or tool-call transcript. The next live Amit P1 stored a validated
  non-fallback case in 3.23 s. New failures retain a sanitized diagnostic in the audit.
- Invalid drafts receive one correction request. Provider errors, step limits or a
  second invalid draft produce a low-confidence engine template. The wall-clock budget
  defaults to 45 s and is configurable with `LLM_INVESTIGATION_BUDGET_SECONDS`.
  Deadlines and API restart recovery mark the job failed and store a template. The
  in-process worker and startup recovery target the single-process API used in the demo.
- `attendflow-agent-smoke <exception_id> --fallback-only` prints the template and
  duration without contacting a provider. The optional real-model pytest requires
  `ATTENDFLOW_REAL_LLM_TEST=1` and `LLM_API_KEY`.

**Worker messages and inbox (Phase 7)**
- `ask-worker` requires a stored investigation routed to the worker. It uses
  verified structured facts to phrase one question, validates the date and
  numbers in the message, and falls back to a template on any model failure.
  The `worker_messages` table retains the message and reply. The receipt and
  `GET /api/worker/messages` only expose worker-facing data.
- Yes assigns the case to the supervisor. No requires details and records
  `needs_actual_time=true`; the case remains `awaiting_worker` and visible
  in the recipient's inbox. Phase 8 validates the actual time before routing
  it to the supervisor.
- The Vite inbox is at `/`. The `/dev` page polls the 202 investigation job,
  then can send a worker question. Review the dev page and its fixed demo
  actors in **Phase 15 (role switcher)** and **Phase 22 (deployment)**.
- `frontend/src/api.generated.ts` comes from FastAPI OpenAPI. Refresh it with
  `npm run api:generate` from `frontend/`. CI checks drift, runs component
  tests and type-checking, and builds the frontend.

**Worker time extraction and re-check (Phase 8)**
- P1 missing clock-outs and P3 wrong clock-outs use the stored clock-out option
  and a verified clock-in. Free text is data. The LLM gets the shift date,
  schedule and clock-in and returns tool-free JSON. Code validates the schema,
  requires one stated time, and checks it against the fixed clock and P15's
  maximum shift length. It accepts an unambiguous approximation for review
  and sends vague, conflicting, or invalid times to the manual form.
- The worker stays assigned until confirming the candidate or submitting an
  exact time. Yes uses the timestamp captured with the question. Both routes
  run the deterministic re-check and store the timestamp, option, source, and
  full result in `worker_recheck`. The inbox shows a code-generated impact
  note only. P1 approval uses the confirmed timestamp and refuses changes to it.
- Invalid model output gets one correction attempt before manual fallback.
  Provider failures use the manual form immediately. `LLM_DIAGNOSTICS=on`
  is the demo default and stores up to 150 sanitized characters of rejected
  output. **Set `LLM_DIAGNOSTICS=off` in real deployments** because worker
  text is personal data. The raw reply audit also requires access controls and
  a retention policy.

**Supervisor approval (Phase 9)**
- Endpoints: `GET /api/supervisor/queue` and `GET /api/supervisor/cases/{id}` (the case
  card). Decisions stay on `POST /api/exceptions/{id}/approve|edit|reject|ask-worker`.
- Queue: a supervisor sees their own team's cases assigned to them that are
  `awaiting_supervisor`, or `open` with a stored investigation whose `who_to_ask` is
  `supervisor`; plus `escalated` cases assigned to them. Priya (payroll admin) sees only
  escalated cases assigned to her (her full list is Phase 10). A case whose latest worker
  message has `needs_actual_time=true` never appears. Sort: severity (high first), date,
  ID.
- Permissions: workers calling any supervisor endpoint (queue, card, approve, edit,
  reject, ask-worker) get 403 `supervisor_only`; that check runs first. Otherwise only
  the person in `assigned_to` may open the card or act (403 `not_assigned`). So Sunita
  cannot touch Ravi's team, and Ravi cannot touch a case escalated to Priya.
- The card is read-only and uses no LLM. It holds the issue, the policy (the
  investigation's verbatim quote, else the policy.md rule), the case worker's own
  evidence only, the worker's raw reply, the confirmed time (`approximate` is stored in
  `worker_recheck`), the stored re-check, and per-option `fields` for the edit form
  (`punches` for P13 `edit_punches`). Other workers' IDs and names in text are replaced
  with "another worker"; supervisors' IDs are not.
- Consequence note per option, built by code in `cases/supervisor.py`: from the worker
  re-check if it is for that option, else from the investigation's stored simulation,
  else "Records a decision only" (decision-only) or "Not checked yet" (unchecked).
  `creates_violations` triggers the UI's confirmation step.
- P9 and P13 options are now `requires_worker_confirmation` (policy: "The worker is asked
  first"). P10 is not: its policy says supervisor approval only.
- A P1 time is approved exactly as the worker confirmed it (the card locks it; a new
  time needs the worker again). P3 corrections can still be edited after a Yes.
  `applied_fix.label` names the time actually applied (not the engine's default).
- Notes: reject reason >= 10 characters (trimmed, 422 `validation_error`); required notes
  of decision-only options >= 3 characters (422 `invalid_params`).
- Audit: approve/edit rows store `before.option_id` + `before.params` and
  `after.applied_fix.params` (also `params_before`) with the reason.
- After an approve/edit that changed data, detection re-runs in its own transaction
  (upsert by ID, so no duplicates). The response has `detection.new_exception_ids` for
  that worker, and the audit gets `post_fix_detection`. If detection fails, the approval
  stands, the audit gets `post_fix_detection_failed`, and the next run picks it up.
- Frontend: `/supervisor` (queue + card, Approve/Edit/Reject, confirmation before a fix
  that creates violations, refusals in plain words). The acting reviewer comes from
  `frontend/src/actors.ts`; in dev builds `?as=E102` or `?as=E201` switches it.
- `.claude/launch.json` starts `api` and `web` for the Claude desktop preview.

**Payroll admin view (Phase 10)**
- Endpoints (payroll admin only; anyone else gets 403 `admin_only`, unknown IDs
  `unknown_actor`):
  - `GET /api/admin/exceptions`: every exception plus `counters` (total, open,
    awaiting_worker, awaiting_supervisor, escalated, resolved, rejected, auto_resolved;
    counted by the database, filters never apply), `matched`, and `filter_options`.
    Filters: `status`, `policy_id`, `team`, `employee_id`, `severity`, `q` (name or ID).
    `sort` = severity (default: severity, date, ID) | date | employee | updated.
    `limit` 200 (max 500) + `offset`. Items carry `investigated`, `who_to_ask`,
    `investigation_fallback` and `needs_your_decision` (escalated and assigned to caller).
  - `GET /api/admin/exceptions/{id}`: read-only detail. Evidence is not redacted (payroll
    sees all). Options reuse `card_options` (Phase 9 consequence note). It includes the
    investigation, `latest_job`, every worker message, the re-check, and the audit trail
    oldest first with a code-built `summary` and before/after status text. Tool calls show
    arguments and outcome only (never output, prompts or keys; a test checks this).
- Code: `cases/admin.py` (no LLM, no writes). Investigating reuses
  `POST /api/exceptions/{id}/investigate`, which already allowed the payroll admin. Priya
  does not ask workers.
- Frontend `/admin` (`AdminPage.tsx`): counters, filters, debounced search, table, detail
  panel, Investigate with polling. For a case escalated to Priya it embeds the exported
  `CaseCard` with `actor=E201`. `adminActor` lives in `actors.ts` (`?as=` dev-only). The
  admin query string is built without `URLSearchParams`, so the Phase 22 bundle grep stays
  meaningful.
- End-to-end tests: `tests/test_e2e_prototype.py` (main story with scripted models,
  reject path, LLM down/invalid at every step, and a SQL write hook proving only
  `fixes/apply.py` and the seed write source data and every fix write is audited).
- Investigation audit rows per job: `structured_investigation_started`, then
  `structured_model_failed` / `structured_draft_rejected` (on failure), then
  `structured_investigation_finished`, then `investigation_case_stored`.
- Demo script with live numbers: [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md).

**Mock device + scheduler (Phase 11)**
- `POST /api/punches` is the mock attendance device. Auth is the `X-Device-Key` header
  checked against `DEVICE_API_KEY` (constant-time compare). A missing or wrong key is
  401 `invalid_device_key`; no key configured is 503 `device_api_not_configured`. The
  body has `employee_id`, `timestamp` (local, no timezone, seconds optional), `type`
  (in/out/break_start/break_end), source `device`, and optional `device_id` and
  `location`. Checks: a known worker (422 `unknown_employee` / `not_a_worker`), not
  after as-of (422 `punch_in_future`), not more than `DEVICE_MAX_BACKDATE_DAYS` (7)
  before it (422 `punch_too_old`), a location from P17 `sites` (422 `unknown_location`),
  and no exact duplicate (same worker, time and type, not voided: 409 `duplicate_punch`).
  Device and location default to the worker's latest device punch (else their team's
  most used one), read from the data.
- **`ingest/punches.py` is the third writer** of source data, after `fixes/apply.py` and
  the seed. It only INSERTs timecards rows, never updates, voids or deletes. Each punch
  gets a `punch_ingested` audit row (actor `device`, no exception ID, `after` = the punch
  + `via` device_api/demo_simulator + `requested_by`) in the same transaction. Punch IDs
  continue `P0073...` under the advisory lock `PUNCH_ID_LOCK` (db/models.py) shared with
  apply.py. Tests: the static check allows exactly this module to use `PunchRow` (insert
  only, two `session.add`), and the SQL write hook allows writer `ingest` only as an
  INSERT into timecards with one matching `punch_ingested` row per new punch.
- After a punch, `service.detect_after_punch` runs detection in its own transaction,
  scoped by `DetectionScope` to that worker and the Mon-Sun week (starting the week of
  the day before, for night shifts). The engine still runs on all data; only rows in
  scope are created, refreshed or closed. Audit: `post_punch_detection` (system), or
  `post_punch_detection_failed` with the error type only; the punch is kept and the
  next full run picks it up.
- Scheduler (`scheduler/cycle.py` + `scheduler/runner.py`): a plain daemon thread in the
  API process, no new dependency. A non-blocking lock means an overlapping cycle is
  skipped and counted, never doubled; run-now while busy is 409 `scheduler_busy`. Each
  cycle: full detection, then investigations (existing job code, actor None = system, one
  at a time, newest detected first, then severity, at most
  `SCHEDULER_INVESTIGATIONS_PER_CYCLE`), then worker messages for open cases routed to the
  worker that were never asked (`ask_worker` with `actor_id=None`, audited as `system`,
  at most `SCHEDULER_MESSAGES_PER_CYCLE`). One failing case is recorded (AppError code +
  message, else the type only) and the cycle goes on. The summary goes to
  `scheduler_runs` (real UTC times) and one `scheduler_cycle` audit row. The system rows
  per case are `auto_investigation_started`, `auto_investigation_finished` and `ask_worker`.
- **Backlog rule (user decision):** by default the scheduler only touches cases first
  detected after the watermark (the max audit ID stored in `settings` as
  `scheduler_watermark` when the scheduler starts, on a demo reset, or on the first cycle
  if neither happened). Older cases are counted in `skipped_backlog` and left alone, so
  Amit's planted P1 stays for the manual walkthrough. `SCHEDULER_BACKLOG=true` processes
  them too.
- Re-investigation: `jobs.finish` stores `exceptions.investigated_facts_hash` (sha256 of
  the detection content fields, `cases/facts.py`). A case is investigated again only if
  it is still open and the hash changed. A template (fallback) case with unchanged facts
  is never retried automatically (keeps Groq quiet); Priya can press Investigate.
- Settings: `SCHEDULER_ENABLED` (false), `SCHEDULER_INTERVAL_SECONDS` (60),
  `SCHEDULER_INVESTIGATIONS_PER_CYCLE` (3), `SCHEDULER_MESSAGES_PER_CYCLE` (3),
  `SCHEDULER_BACKLOG` (false), `DEVICE_API_KEY`, `DEVICE_MAX_BACKDATE_DAYS` (7),
  `ATTENDFLOW_DEMO_MODE` (false), `ATTENDFLOW_CORS_ORIGINS` (default the Vite :5173
  origins). Tests force these in `api_settings`, whatever `.env` says.
- Endpoints (payroll admin only, else 403 `admin_only`): `GET /api/admin/scheduler`
  (status, last cycle, watermark, as-of, demo mode, workers for the simulator),
  `POST .../run-now`, `POST .../start`, `POST .../stop` (runtime only; start moves the
  watermark).
- **DEMO_MODE** (`ATTENDFLOW_DEMO_MODE=true`) adds `demo_router`: `POST
  /api/admin/demo/reset` (seed + detection + watermark; the caller must exist, so an
  empty DB needs `POST /api/seed` once) and `POST /api/admin/demo/punch` (the same
  ingest path as the device, `via=demo_simulator`, no device key in the browser). With
  demo mode off these routes are not registered (404). OpenAPI types are generated with
  demo mode on (`scripts/generate-api.mjs`), independent of `.env`.
- Frontend: `/admin` has `SchedulerPanel` (status line, Run scheduler now; in demo mode
  also the Simulate punch form). While the simulator is open it refreshes the list and
  status every 4 s. The worker inbox takes a dev-only `?as=E004` (Neha), the same way as
  the reviewer override.
- Demo scenario: Neha (E004) clocks in Wed 15 Apr **08:58** (not 09:02, which would add an
  auto-resolved P7 within grace) with no clock-out. This gives a fresh
  `P1-E004-2026-04-15` and closes her planted `P10-E004-2026-04-15`. The P1 routes to the
  worker, so one cycle investigates it and messages Neha.
- Detection already auto-resolves P2 and P7 within grace (Phase 3 behaviour), including
  after a device punch. Phase 12 added the guard, snapshot, undo and metric.

**No-reply escalation (Phase 13)**
- Clock split (`clock.py`): `clock.now()` stamps rows and drives timeouts;
  `data_as_of(clock)` is the data cut-off for detection, fixes, worker time checks and
  device punches, and never moves. The app uses `DemoClock(as_of)` (offset 0 = the old
  fixed clock). Demo mode only: `GET/POST /api/admin/demo/clock` (payroll admin; forward
  only, max +14 days, 422 `clock_limit`; audited `demo_clock_moved`; runs nothing). The
  offset is stored in `settings` (`demo_clock`), restored at startup, zeroed by demo reset.
- Ladder (`cases/no_reply.py` rules, `cases/ladder.py` runner): step 4 of every scheduler
  cycle (timer or run-now, timer off is fine). Stage 0 -> 1 reminder at N h, 1 -> 2 the
  team supervisor at M h (awaiting_worker -> awaiting_supervisor), 2 -> 3 payroll admin K h
  after stage 2 if the case is still awaiting_supervisor (-> escalated, E201). N and M
  count from `no_reply_wait_since` (question sent, or a No that still needs the time); K
  from `no_reply_supervisor_at`. Fires at the limit, never before; one step per case per
  check, never skipping (a clock jump still gets the reminder first). Row lock + stage
  check = each step once per wait. Covers EVERY awaiting_worker case, hand-asked and
  backlog included (user decision: the watermark does not apply); undone cases skipped.
  Kill switch `NO_REPLY_ESCALATION_ENABLED`. Audit (actor system, `due_at` + `fired_at`):
  `no_reply_reminder`, `no_reply_to_supervisor`, `no_reply_to_admin`. Migration `0008`
  (exceptions `no_reply_stage` + 5 timestamps; worker_messages `reminded_at`,
  `reminder_text`; backfills the wait start of waiting cases).
- Reminder text is a fixed template (user wording): "Reminder: we still need your answer
  about {date}. If we don't hear from you by {deadline}, your supervisor will review it
  using the records." Stored on the question it reminds about.
- Replies: any worker reply stops the ladder (`no_reply_ladder_stopped`, written after the
  reply row). At stage 2 the question stays answerable: Yes runs the Phase 8 re-check and
  stays with the supervisor ("Replied late", `no_reply_late_reply_at`); No goes back to the
  worker for the time (awaiting_supervisor -> awaiting_worker) and starts a new wait.
  At stage 3 (or after a manual escalate) it is closed: 409 `handled_by_payroll`. Asking
  again starts a new wait. `needs_actual_time` is kept (so a late time still works); the
  queue shows stage 2+ cases even with it set.
- Decide without the worker: approve/edit with `without_worker: true`, only at stage 2+
  for the assignee (else 409 `no_reply_not_escalated`), reason >= 10 chars (422
  `reason_required`), and for any punch-time option (set_clock_in/out, correct_clock_out;
  the user asked for P1, applied to all time options) `confirm_time_without_worker`
  (422 `time_confirmation_required`). Phase 8 time validation still runs; `apply.py` still
  writes. `applied_fix.without_worker` = reason, stage, hours, time, `time_source`
  prefilled/edited; extra audit row `decided_without_worker`. Silence never counts as Yes.
- `POST /api/exceptions/{id}/escalate` (reason >= 10): the assignee supervisor sends any
  non-final case to payroll without rejecting; audit `escalate_to_admin`.
- Worker inbox now returns `{items, notices}`: items carry `reminder` and `status_note`;
  notices are "Decided without your reply" (with the reason) and "With payroll".
- Views: queue/card `no_reply` (`NoReplyOut`: stage, label, note "X has not replied for
  N h", times, `can_decide_without_worker`); admin list item + detail `no_reply`, counter
  `stuck` (stage > 0 and not final), filter `no_reply=any|reminded|supervisor|payroll_admin`.
- policy.md (user-approved): P1, P3, P4, P9, P13 "Allowed fixes" end with "If the worker
  does not reply in time, the supervisor may decide on the evidence."
- Live check: `attendflow_phase13` DB, API :8013, Vite :5185 (`.claude/launch.json`
  configs `api-phase13` / `web-phase13`).

**Auto-resolve + undo (Phase 12)**
- Only P2 and P7 (within grace) may close without a person: `AUTO_RESOLVABLE` in
  `policy/models.py`; `policy.json` with `auto_resolve: true` on any other policy fails to
  load. `engine/auto_resolve.py` (last engine step) adds `details.auto_resolve` =
  `{basis, eligible, held_because}` and holds for a person: taps spanning more than the
  P2 window (chained), taps from two devices or locations, a second clock-in (P7), or a
  punch in any P17 case. Boundaries: P2 5:00 apart is a duplicate, 5:01 is not; P7 10:00
  late is within grace, 10:01 is a late arrival.
- Kill switch `AUTO_RESOLVE_ENABLED` (default true), passed as `auto_resolve=` to every
  `run_detection` / `detect_after_*` call. Off (or engine-held): stored open with an
  `auto_resolve_held` audit row. Only NEW rows are ever auto-resolved.
- Human options on these cases: P2 `void_duplicate` (`void_punches`); P7 the new
  decision-only `confirm_within_grace` (no "record as late": policy.md says within grace
  is not late).
- Snapshot: `apply_auto_resolve` returns the `applied_fix` with `snapshot_version` 1, each
  change's full `before`/`after` row and `guarded_rows` (other evidence punches).
- Undo: `POST /api/exceptions/{id}/undo` (`UndoIn.reason` >= 10 chars). Payroll admin any
  case; supervisor only their team (403 `not_assigned`); workers 403 `supervisor_only`.
  `fixes/apply.py undo_auto_resolve` restores only if every stored row still matches;
  the service also refuses if another case's audited fix (approve/edit/auto_resolve/undo)
  touched the worker's punches on that shift date (day + next morning) after the
  auto-resolve (read via `apply.punches_fixed_by_others`). Refusal = 409 `undo_conflict`
  or `undo_unavailable` (no snapshot), nothing changed, one `undo_refused` audit row.
  Also 409 `not_auto_resolved`, `already_undone`.
- After undo: `resolved -> open` (undo-only transition, `transitions.UNDO`), assigned to
  the worker's supervisor, `auto_resolved=false`, `applied_fix=None`,
  `auto_resolve_undone_at/by` set (migration `0007`), audit `auto_resolve_undone`
  (before has the undone `applied_fix`), then `post_undo_detection` if data was restored.
  The supervisor queue shows undone open cases; the scheduler never investigates or
  messages them, even with backlog on (`skipped_undone`).
- Metric `GET /api/admin/metrics/auto-resolve` (payroll admin): X =
  `resolved_without_human` (auto_resolved, so not undone), Y = `needed_handling` (all
  minus `closed_by_data_change` = resolved rows with a `no_longer_detected` audit row),
  `percent`, `undone`, `by_policy`, optional `date_from`/`date_to`. The Auto-resolved
  counter tile equals X.
- `cases/auto_fix.py`: `auto_fix_info` (admin detail `auto_fix`), `team_auto_fixes`
  (`GET /api/supervisor/auto-resolved`), `metric`. Frontend `AutoFix.tsx`:
  `AutoResolveMetricLine`, `AutoFixPanel` (Undo with reason, plain refusal text),
  `TeamAutoFixes` on `/supervisor`.
- Live check ran on a separate DB (`attendflow_phase12`, API :8012, Vite :5184; launch
  configs `api-phase12` / `web-phase12`) because another session used the dev DB.

**Activity Center + Autonomy Table (Phase 14)**
- One source of truth: the feed reads `audit_log` only (joined to the case and employees),
  newest first, paged by `before_id` (default 50, max 200). No new table, no migration.
  Times are workflow times (`created_at`, demo clock).
- `activity/autonomy.py` is the registry: one `Capability` per action with actor type
  (code / llm_agent / system / device / human), approval (none / supervisor /
  payroll_admin / supervisor_or_payroll_admin), reversible (yes_undo / no /
  not_applicable), guardrail, its `(audit_actions, audit_actors)` and `proof_tests`, plus
  6 "never" rows. `ask_worker` is two rows told apart by actor (scheduler vs person).
- Anti-drift (`tests/test_autonomy.py`, `tests/test_activity.py`): an AST scan finds every
  audit write in the backend (f-strings only with a `Literal`-typed parameter, so
  `detect_after_fix(after: Literal["fix", "undo"])`) and checks both directions; a
  session-wide SQLAlchemy listener (`tests/audit_guard.py`, wired in conftest) fails any
  test that writes an unmapped `(action, actor)` pair; rows that need a person name tests
  that must contain a refusal or data-safety assertion; autonomous rows must happen with
  their actor in the shared end-to-end story (`tests/activity_story.py`) or name the test
  that covers them; the README block must equal the registry's output.
- README "Autonomy and guardrails" is generated between markers by
  `attendflow-autonomy --write-readme`; `--check` runs in CI.
- Who sees what (API): Priya everything; a supervisor only rows of cases whose worker
  reports to them (rows without a case are payroll-only); workers 403 `supervisor_only`.
  `scheduler_cycle` rows are hidden from the feed.
- Safety: feed items never carry before/after, tool input/output, prompts or message
  bodies. `reason` only for a person's own typed reason (approve, edit, decide without,
  reject, escalate, undo). `structured_model_failed` / `structured_draft_rejected` /
  extraction rejections get fixed sentences (no diagnostic, no preview). Tested with
  LLM_DIAGNOSTICS on.
- Summary strip (same scope and filters, not actor/mode): investigated (distinct cases
  with `investigation_case_stored`), messages sent, reminders, auto-resolved (+ undone),
  escalated by silence (distinct cases), approvals (+ decided without the worker),
  rejections, device punches.
- Case links: Priya gets the `/admin` detail; a supervisor gets the existing case card,
  now readable for any own-team case (`can_decide`), with a compact `trace` (tool name +
  a code-built `result_summary`). `/admin` tool calls also show `result_summary`.
- The reported Phase 13 "tool calls stamped 08:00" gap does not reproduce through the API
  (test `test_agent_rows_use_the_moved_demo_clock`); only the standalone
  `attendflow-agent-smoke` CLI (`agent/loop.py`) uses the fixed as-of clock.
- Live check ran on `attendflow_phase14` (API :8001, Vite :5174, launch configs
  `phase14-api` / `phase14-web` in `.claude/launch.json`). In PowerShell `$env:X=''`
  deletes the variable, so an "empty" LLM key falls back to `.env`; point
  `LLM_BASE_URL` at an unreachable address instead to keep a live check offline.

## Repo map

```
backend/attendflow/
  config.py              Settings from env/.env (as-of, data dir, LLM)
  data/schemas.py        Pydantic row model per CSV (strict formats, no tz, no extra cols)
  data/loader.py         load_dataset(): row + cross-file validation, all errors at once
  policy/models.py       load_policy() (P1-P17, required params), load_policy_text() for policy.md
  engine/models.py       Shift, TimecardException, FixOption, EngineResult (Pydantic)
  engine/shifts.py       P2 de-dup, then punches -> shifts (P15 windows), scheduled_hours()
  engine/rules.py        RuleContext (leave-adjusted schedule), helpers, checks P1-P7
  engine/rules_schedule.py  P8, P10, P14, P16
  engine/rules_leave.py  P9, P11, P12, P13
  engine/rules_review.py P17 possible punch conflict
  engine/checks.py       ordered CHECKS registry + the check-order note
  engine/auto_resolve.py last engine step: which P2/P7 candidates may auto-resolve (or held)
  engine/engine.py       build_context() + run_engine(dataset, policy, as_of) -> EngineResult
  llm/client.py          OpenAI-compatible chat()/chat_once()/list_models(); bounded retry
  agent/loop.py          Native tool calls over one stored exception, returns AgentRun
  agent/journal.py       Separate write sessions for tool call and audit rows
  clock.py               Clock: now() (row stamps, timeouts) + data_as_of() (fixed data cut-off);
                         FixedClock, DemoClock (as-of + a demo-only forward offset)
  demo_clock.py          demo clock offset: describe, load at startup, move (audited), reset
  ingest/punches.py      the ONLY other writer: new device punches (INSERT + audit row)
  scheduler/cycle.py     one cycle: detect, investigate new cases, message workers, no-reply ladder,
                         summary
  scheduler/runner.py    Scheduler thread, non-overlap lock, start/stop/status
  errors.py              AppError family -> HTTP status + error code
  db/models.py           SQLAlchemy tables (6 source tables + exceptions, audit_log, tool_calls,
                         settings, scheduler_runs); PUNCH_ID_LOCK
  db/migrations/         Alembic (alembic.ini at repo root)
  db/seed.py             demo reset: truncate all, load CSVs
  db/dataset.py          read-only: DB -> engine Dataset (voided punches left out)
  fixes/params.py        Pydantic params per fix action; decision-only action list
  fixes/apply.py         the ONLY writer of timecards/schedule/leave after approval (and auto-resolve
                         + its undo, with before/after snapshots)
  cases/transitions.py   status flow table + check_transition()
  cases/service.py       run_detection (upsert, optional DetectionScope), approve/edit, reject,
                         ask_worker (also as system), worker_reply, detect_after_fix,
                         detect_after_punch
  cases/facts.py         CONTENT_FIELDS + facts_hash() (re-investigate only on changed facts)
  cases/supervisor.py    supervisor queue, case card, consequence note, reviewer permission
  cases/admin.py         payroll admin overview, counters, read-only case detail, audit summaries
  cases/auto_fix.py      auto-resolve info per case, supervisor team list, "without a human" metric
  cases/no_reply.py      no-reply ladder rules (due_step), wait state, reminder text, NoReply view
  cases/ladder.py        runs one ladder step per due case (scheduler step 4); no data writes
  activity/autonomy.py   the Autonomy Table registry (single source) + README rendering
  activity/feed.py       Activity Center feed, summary counts, team scope, safe sentences
  activity/trace.py      one-line tool-call result summaries for the case traces
  tools/models.py        tool inputs/outputs (Pydantic), ok/error envelope, ProposedChange
  tools/read_tools.py    get_schedule, get_leave, get_leave_balance, get_punches, get_policy
  tools/run_checks.py    run_checks: simulate a change, re-run the engine, diff the week
  tools/simulate.py      in-memory copy of the fix appliers (never touches the DB)
  tools/registry.py      TOOLS + openai_tools() (OpenAI function-calling, flattened schemas)
  tools/runner.py        ToolRunner: validate, load read-only, call, on_call hook
  tools/context.py       ToolContext + read_only_session()
  api/app.py             create_app(), error handlers, request logging, attendflow-api
  api/routes.py          /api endpoints;  api/schemas.py request/response models
  scripts/               generate_data, validate_data, llm_smoke_test, detect, tools_cli,
                         autonomy_cli (CLIs)
data/                    6 CSVs + policy.json (limits) + policy.md (plain-language, cited by agent)
docs/                    PROGRESS.md, PLANTED_CASES.md, LLM_LICENCE.md, DEMO_WALKTHROUGH.md
tests/                   pytest suite
frontend/                Vite React: worker inbox (/, reminders + notices), supervisor (/supervisor,
                         no-reply badge, decide without worker, send to payroll, TeamAutoFixes),
                         admin (/admin, SchedulerPanel with demo clock, stuck counter + filter,
                         metric line, AutoFixPanel), activity (/activity: feed, filters, summary
                         strip, Autonomy tab), dev (/dev)
docker-compose.yml       PostgreSQL 16 (host port 5433); docker/initdb creates the test DB
.github/workflows/ci.yml lint + validate + README autonomy check + tests (Postgres service)
```

## Commands

```bash
python -m uv sync                          # install
python -m uv run attendflow-validate       # validate CSVs + policy files
python -m uv run attendflow-detect         # rule engine table (--fixes, --json, --employee E002, --policy P11,P12)
python -m uv run attendflow-llm-test       # one prompt to the model (add --list-models)
python -m uv run attendflow-generate-data  # rebuild data/*.csv
docker compose up -d db                    # PostgreSQL (port 5433)
python -m uv run alembic upgrade head      # create/upgrade tables
python -m uv run attendflow-api            # API on http://localhost:8000/docs
python -m uv run attendflow-autonomy --write-readme  # regenerate README "Autonomy and guardrails" (--check in CI)
python -m uv run attendflow-tools list     # agent tools (get_punches employee_id=E001 date=2026-04-14; --csv)
# Set AGENT_MAX_STEPS=6 in your shell for this sequential Groq smoke.
python -m uv run attendflow-agent-smoke P1-E001-2026-04-14
python -m uv run pytest                    # tests (API tests need the db container)
# Device punch (needs DEVICE_API_KEY in .env and the API running):
curl -X POST localhost:8000/api/punches -H "X-Device-Key: $DEVICE_API_KEY" -H "Content-Type: application/json" -d '{"employee_id":"E004","timestamp":"2026-04-15T08:58","type":"in"}'
# Demo clock (ATTENDFLOW_DEMO_MODE=true), then run a cycle to apply the no-reply steps:
curl -X POST localhost:8000/api/admin/demo/clock -H "X-Actor-Id: E201" -H "Content-Type: application/json" -d '{"hours":8}'
curl -X POST localhost:8000/api/admin/scheduler/run-now -H "X-Actor-Id: E201"
python -m uv run ruff check . && python -m uv run ruff format --check .
```
