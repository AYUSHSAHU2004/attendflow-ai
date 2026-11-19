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
3 Backend + DB + API; 4 Read-only tools + fix options for P3/P4/P6/P7; 5 LLM client + agent loop; 6 structured investigations and jobs; 7 worker messages and inbox; 8 worker clock-out extraction and re-check.

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

**Next: Phase 9.**

**Carry-over notes**
- Phase 5 Groq bug: `run_checks` advertised Pydantic's RFC 3339 `date-time` format for
  timezone-free local timestamps. Groq rejected minute-precision values with HTTP 400.
  The schema now advertises the app's local time patterns; the registry tests check
  every tool schema recursively for unsupported formats and schema references.
- Phase 9: Review whether P9, P10 and P13 should have the same worker confirmation
  guard as P1. Their policy text says the worker is asked first.
- Phase 22: `POST /api/seed` wipes every table. It must be disabled
  (`ATTENDFLOW_ENABLE_SEED=false`) or protected on the deployed server.

## Decisions so far (do not re-ask)

**Environment**
- Project path: `C:\dev\attendflow-ai`. It was moved out of OneDrive to avoid sync and lock
  problems. GitHub: https://github.com/AYUSHSAHU2004/attendflow-ai (branch `main`).
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
  engine/engine.py       build_context() + run_engine(dataset, policy, as_of) -> EngineResult
  llm/client.py          OpenAI-compatible chat()/chat_once()/list_models(); bounded retry
  agent/loop.py          Native tool calls over one stored exception, returns AgentRun
  agent/journal.py       Separate write sessions for tool call and audit rows
  clock.py               FixedClock: the only source of "now" (ATTENDFLOW_AS_OF)
  errors.py              AppError family -> HTTP status + error code
  db/models.py           SQLAlchemy tables (6 source tables + exceptions, audit_log, tool_calls, settings)
  db/migrations/         Alembic (alembic.ini at repo root)
  db/seed.py             demo reset: truncate all, load CSVs
  db/dataset.py          read-only: DB -> engine Dataset (voided punches left out)
  fixes/params.py        Pydantic params per fix action; decision-only action list
  fixes/apply.py         the ONLY writer of timecards/schedule/leave after approval
  cases/transitions.py   status flow table + check_transition()
  cases/service.py       run_detection (upsert), approve/edit, reject, ask_worker, worker_reply
  tools/models.py        tool inputs/outputs (Pydantic), ok/error envelope, ProposedChange
  tools/read_tools.py    get_schedule, get_leave, get_leave_balance, get_punches, get_policy
  tools/run_checks.py    run_checks: simulate a change, re-run the engine, diff the week
  tools/simulate.py      in-memory copy of the fix appliers (never touches the DB)
  tools/registry.py      TOOLS + openai_tools() (OpenAI function-calling, flattened schemas)
  tools/runner.py        ToolRunner: validate, load read-only, call, on_call hook
  tools/context.py       ToolContext + read_only_session()
  api/app.py             create_app(), error handlers, request logging, attendflow-api
  api/routes.py          /api endpoints;  api/schemas.py request/response models
  scripts/               generate_data, validate_data, llm_smoke_test, detect, tools_cli (CLIs)
data/                    6 CSVs + policy.json (limits) + policy.md (plain-language, cited by agent)
docs/                    PROGRESS.md, PLANTED_CASES.md, LLM_LICENCE.md
tests/                   pytest suite
frontend/                Vite React worker inbox and dev supervisor page
docker-compose.yml       PostgreSQL 16 (host port 5433); docker/initdb creates the test DB
.github/workflows/ci.yml lint + validate + tests (with a Postgres service) on Python 3.12
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
python -m uv run attendflow-tools list     # agent tools (get_punches employee_id=E001 date=2026-04-14; --csv)
# Set AGENT_MAX_STEPS=6 in your shell for this sequential Groq smoke.
python -m uv run attendflow-agent-smoke P1-E001-2026-04-14
python -m uv run pytest                    # tests (API tests need the db container)
python -m uv run ruff check . && python -m uv run ruff format --check .
```
