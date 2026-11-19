# Progress log

Project path: the repo root (the path differs per machine). Repo: https://github.com/AYUSHSAHU2004/attendflow-ai.
Standing rules and all decisions: [../CLAUDE.md](../CLAUDE.md).

## Phase 0: Project setup, sample data, policy files, LLM test (2026-11-19) ✅

**Built**
- Repo skeleton (`backend/`, `frontend/`, `data/`, `docs/`, `tests/`), README, CLAUDE.md,
  `.env.example`, git-ignored `.env`, and a GitHub Actions CI workflow (lint, data
  validation, tests).
- Python package `attendflow`:
  - `data/schemas.py`: Pydantic row models for all 6 CSVs, with strict date, time and
    timestamp formats. Timezone offsets are rejected. Extra columns are rejected, so a
    stored leave "balance" column fails.
  - `data/loader.py`: loads everything and runs cross-file checks (unknown employee IDs,
    supervisors, duplicates, leave without a balance row). It reports all errors at once.
  - `policy/models.py`: typed `policy.json` loader (all of P1-P16 present, required params,
    positive limits) and a `policy.md` section splitter for later citation.
  - `llm/client.py`: thin OpenAI-compatible client. Every failure becomes `LLMError`, so
    later phases can fall back to templates.
  - CLI tools: `attendflow-generate-data`, `attendflow-validate`, `attendflow-llm-test`.
- Demo data: 10 workers in 2 teams, plus Ravi and Sunita (supervisors) and Priya (payroll
  admin). All 8 planted cases plus controls are in [PLANTED_CASES.md](PLANTED_CASES.md).
- `data/policy.json` (limits) and `data/policy.md` (plain-language policy, one section per ID).
- 46 tests: validation failure modes, policy integrity, planted-case fixtures and the LLM
  client using a fake client.

**Decisions**
- **Environment:** the project lives at the repo root (the path differs per machine), kept
  out of OneDrive to avoid sync and lock problems. It uses Python **3.12** via **uv**, with dependencies
  locked in `uv.lock`. The machine's default is Python 3.14, which is too new for some
  libraries, and `uv` is not on PATH, so commands use `python -m uv`.
- **LLM:** **`openai/gpt-oss-120b`** (open-weight, **Apache 2.0**) on Groq. The plan was
  Llama 3.3 70B, but Groq retired it (checked 2026-11-19). The user chose gpt-oss-120b over
  Qwen 3.8 27B: it is the largest model on offer, strong at tool calling, and has a
  permissive licence. See [LLM_LICENCE.md](LLM_LICENCE.md).
- **Demo week:** Mon **13 to Sun 19 Apr 2026**. The holiday is Tue 14 Apr (Ambedkar
  Jayanti). Amit and Meena are on holiday duty; everyone else is off.
- **As-of time:** **Thu 16 Apr 2026, 08:00** (`ATTENDFLOW_AS_OF` in `.env`). Mon-Wed is the
  past and Thu-Fri is the forecast, so Meena's overtime shows as a *risk* before it happens.
- **Expected side-effect flags**, documented in PLANTED_CASES.md:
  - Meena: P5 risk, plus P3 on Mon, Tue and Wed (12 h days) and P14 on Tue (holiday duty).
  - Sana: P2 Monday, plus P14 and P8 on Tue (unscheduled holiday work).
  - Amit: P1 Tue, plus P14 (the missed clock-out is on the holiday).
- **P16 (max 6 consecutive days): no planted demo case**, and none for P6 either. The user
  accepted the default. Both will be tested with small synthetic fixtures in the engine
  phase. A demo case can be added to the generator if wanted.
- The data comes from a deterministic generator (seed 42). A test fails if a CSV is
  hand-edited.
- `attendflow-validate` checks that every numeric limit in `policy.json` appears in
  `policy.md`, so the text the agent cites cannot drift from the limit the code enforces.
- Only P2 and P7 (within grace) are marked `auto_resolve` in `policy.json`.

**How to run and verify** (from the repo root)
```bash
python -m uv sync                                   # install (first time)
python -m uv run attendflow-validate                # expect "OK: all data files are valid."
python -m uv run attendflow-llm-test --list-models  # expect a reply from gpt-oss-120b
python -m uv run pytest                             # expect 46 passed
```
CI runs the same lint, validation and test steps on every push to GitHub.

**Next: Phase 1**
- Deterministic rule engine: group punches into shifts (P15), compute hours, and detect
  P1-P16 using `policy.json` limits only. Use PLANTED_CASES.md as the expected output, and
  synthetic fixtures for P6 and P16.

## Phase 1: Deterministic rule engine, P1-P7 and P15 (2026-11-19) ✅

**Built**
- `attendflow.engine` package (plain code, no LLM):
  - `shifts.py`: drops punches after the as-of time, removes duplicate taps (P2), then
    groups punches into shifts. Each punch joins the scheduled shift whose window holds it
    (4 h before start to 6 h after end), so night shifts stay whole and are dated by their
    start day (P15). Unscheduled punches are grouped from clock-in to clock-out.
  - `rules.py`: one check per policy, P1-P7. Each exception has severity, kind
    (breach/risk), status (open/auto_resolved), a one-line summary, `details` (the numbers
    and the limit used), `evidence` (the punch rows) and `fix_options`.
  - `engine.py`: `run_engine(dataset, policy, as_of)`, deterministic and sorted.
- CLI `attendflow-detect`: table of employee, date, policy, severity, status, numbers.
  Options: `--fixes`, `--json`, `--employee`, `--as-of`, `--data-dir`.
- 45 new tests (91 total): pass/fail cases per policy with small synthetic fixtures
  (P6 included), boundaries, the night shift, the answer key on the demo data, a
  "change policy.json, no code edit" test and CLI output tests.

**Decisions**
- Scope: P1-P7 + P15 only; P8-P14 and P16 move to Phase 2.
- New params in `policy.json`, mirrored in `policy.md` (the validator enforces this):
  P1 `open_shift_grace_hours` 4, P5 `planned_break_after_hours` 6 and
  `planned_break_minutes` 60, P15 `match_before_start_hours` 4, `match_after_end_hours` 6,
  `max_shift_hours` 16. The P5 lunch deduction is what makes Amit's week exactly 40 h (no
  flag) and Meena's 36 + 12 = 48 h.
- Limits are broken only when strictly exceeded. A missing-punch shift is skipped by P3/P4
  and counted at its scheduled hours for P5.
- P5 and P6 forecast from the schedule: `kind = risk` before it happens, `breach` after.
- P7 also checks early leave (from the full Phase 1 brief). Late within grace becomes an
  auto-resolved record; early leave within grace is ignored, so Amit's 2-5 min early
  clock-outs stay clean.
- `fix_options` filled for P1 (set clock-out to scheduled end, or clock-in to scheduled
  start) and P5 (approve the overtime, or cut the exact hours from the latest upcoming
  shifts: Meena Fri 6 -> 0 h, Thu 6 -> 4 h). Empty for the others for now.
- Ramesh's shift spans 21:58-06:00 (8 h) and is one shift; worked hours are 7.53 after his
  30 min break.

**How to run and verify** (from the repo root)
```bash
python -m uv sync
python -m uv run attendflow-detect --fixes   # expect 8 exceptions, Meena "36 h + 12 h = 48 h ... over by 8 h"
python -m uv run pytest                      # expect 91 passed
```
Done-when check: the table shows exactly Amit P1 (Tue), Meena P3 (Mon/Tue/Wed) + P5,
Neha P4 (Mon), Sana P2 (Mon, auto-resolved), Karan P7 (Mon). No Ramesh, Arjun or Pooja.

**Next: Phase 2**
- P8-P14 and P16 (holidays, leave conflicts, absences, leave balance and certificates,
  consecutive days), with a synthetic fixture for P16.
- Make the P5 forecast leave-aware (Dev's scheduled Thursday is a sick day but still counts
  as 8 forecast hours today).

## Phase 2: Advanced rules P8-P14, P16 and P17 punch review (2026-11-19) ✅

**Built**
- New rule modules, extending the Phase 1 engine (no rewrite):
  - `rules_schedule.py`: P8 unscheduled work, P10 unexplained absence, P14 holiday work,
    P16 consecutive days (breach from punches, risk from the upcoming schedule).
  - `rules_leave.py`: P9 punches on a full-day leave, P11 leave over balance (balance is
    computed as total - used), P12 sick run without a certificate (sorted first; holidays
    and days off don't break a run), P13 half-day leave vs hours worked.
  - `rules_review.py`: new **P17 "Possible punch conflict, needs review"**: same terminal at
    the same second, two sites less than 60 min apart, and an app punch from an unapproved
    location. It never says "fraud" (a test checks this).
  - `checks.py`: ordered registry of all checks, with a note on the check order.
- **Check order:** leave is applied to the schedule when the rule context is built, before
  any check runs. P5, P6 and P16 forecasts never count a leave day. This fixes Dev's sick
  Thursday (now 0 h).
- Every new exception has severity, details, evidence and fix_options. Evidence can now
  include leave, balance, schedule and holiday rows, not only punches.
- CLI: `--policy P11,P12` filter and a "By policy" count line.
- 63 new tests (154 total): pass and fail cases for every new check, boundaries, the
  check-order test, the full answer key on the demo data, and the CLI Done-when output.

**Decisions** (all defaults accepted, plus one addition)
- P14 severity is **low** for planned holiday duty (Amit, Meena) and **medium** for
  unscheduled holiday work (Sana, together with P8). This is a policy.json param.
- Seconds on punches: the generator gives each worker a fixed offset (0 to -29 s) on all
  of their punches. Without it, the round-minute demo data had about 10 false "same second"
  clashes. Durations, punch IDs and the Phase 1 answer key are unchanged.
- P17 config in policy.json: `sites` (location -> site), `approved_app_locations`,
  `location_switch_minutes` 60, `same_second_min_employees` 2. App punches are not compared
  for "same second". No planted demo case (synthetic tests only).
- P9 and P13 also flag **pending** leave. P10 waits for scheduled end + 4 h grace. P7 skips
  leave days. P13 uses 4 h ± 1 h (`tolerance_hours`). P14 counts national and company
  holidays; comp-off is 0.5 day if 4 h or less. P11 counts pending days; the balance pays
  the earliest dates first.
- Phase 1 test edits (assertions unchanged): `test_engine_demo.py` now runs P1-P7 only,
  because the default run includes Phase 2 policies. One validation test points at Meena's
  new first timestamp (`06:59:47`).
- CSV row models now dump JSON in their CSV formats (`09:00`, `yes`), so the engine JSON
  loads back. A round-trip test found this.

**How to run and verify** (from the repo root)
```bash
python -m uv run attendflow-generate-data           # data unchanged after this (a test checks it)
python -m uv run attendflow-validate                # expect 17 policies, "OK"
python -m uv run attendflow-detect --fixes          # expect 17 exceptions (16 open, 1 auto-resolved)
python -m uv run attendflow-detect --policy P1,P2,P3,P4,P5,P6,P7   # Phase 1 view: the same 8 as before
python -m uv run pytest                             # expect 154 passed
```
Done-when check: Dev shows "Sick leave applied 3, balance 1" (P11) and "3 sick days in a
row ... no medical certificate" (P12). Karan shows P9 on Wed. Sana shows P8 + P14 on Tue.
Farah shows P13 (8.03 h on a half-day leave). Amit and Meena show P14 (low). Ramesh, Arjun
and Pooja show nothing.

**Next: Phase 3** (under the new phase plan below)
- Backend + DB + API: PostgreSQL, FastAPI and the first API endpoints over the engine results.
- Still open: fix_options for P3, P4 and P7 (now Phase 4); an optional P17 demo case.

## Phase plan change (2026-11-19)

The plan was renumbered after Phase 2. The LLM layer, previously "Phase 3", is now split
across Phases 5-8. Phases 0-2 are done; next is Phase 3. The same list is in
[../CLAUDE.md](../CLAUDE.md#phase-plan).

| # | Phase | | # | Phase |
|---|---|---|---|---|
| 3 | Backend + DB + API | | 14 | Activity Center + autonomy table |
| 4 | Read-only tools + fix options for P3/P4/P7 | | 15 | Role switcher + Priya dashboard |
| 5 | LLM client + agent loop | | 16 | Payroll readiness |
| 6 | InvestigationCase schema + fallback + `/investigate` | | 17 | Briefing + Amit mobile + summary |
| 7 | Worker message + Amit page | | 18 | Settings backend |
| 8 | Free-text extraction + re-check | | 19 | Admin UI |
| 9 | Ravi's approval | | 20 | Employee Q&A |
| 10 | Priya's plain list + integration test (**prototype done**) | | 21 | Analytics |
| 11 | Mock punch API + scheduler | | 22 | Deployment |
| 12 | Auto-resolve + undo | | 23 | Tests + evaluation |
| 13 | No-reply escalation | | 24 | Delivery |

## Phase 3: PostgreSQL schema and FastAPI backend (2026-11-19) ✅

**Built**
- PostgreSQL 16 in Docker (`docker-compose.yml`, host port 5433) with a separate test
  database. SQLAlchemy 2 tables + an Alembic migration (`0001_initial_schema`):
  - Source data, one table per CSV. Punches get `voided`, `voided_by_exception` and
    `created_by_exception`; leave rows get a DB-only `unpaid` flag.
  - `exceptions` (the engine ID is the primary key, so detection never duplicates),
    `audit_log`, `tool_calls` and `settings`. Status, actor, severity and kind are CHECK
    constraints in the database too.
- `db/seed.py`: full demo reset from the CSVs (validated first; nothing is wiped if a CSV
  is bad). `db/dataset.py`: the engine now runs on the database.
- `cases/service.py`: detection upsert, approve, edit, reject, ask-worker, worker-reply.
  Each call is one transaction. `cases/transitions.py`: the status flow table.
- `fixes/apply.py`: writes approved fixes (14 data actions: punch corrections, schedule
  cuts, rest days, leave record/cancel/convert/split/move/reject). 10 decision-only actions
  are recorded without data changes. Guards: punches must be on the shift day and not in
  the future, only upcoming shifts can change, leave balances must have room, stale fixes
  are refused (409 `stale_fix`).
- FastAPI app (`attendflow-api`), 12 endpoints under `/api`, OpenAPI docs at `/docs`,
  one error shape, JSON logs with request IDs.
- 108 new tests (262 total): every endpoint, every status pair, permissions, each fix
  writer, idempotent detection, "a rejected fix leaves the timecard unchanged", a forced
  failure that rolls back the fix, a write-guard test, and a migration-vs-models check.
  CI now runs a Postgres service and fails if the API tests would be skipped.
- Safety guard: the tests refuse any database whose name does not end in `_test`, so a
  mistyped `TEST_DATABASE_URL` can never wipe the dev database.

**Decisions** (all 17 defaults, with the user's changes)
- **Reject:** a supervisor's reject moves the case to `escalated` and assigns it to the
  payroll admin (E201), with the reason in the audit log. On an escalated case the
  assignee may approve, edit or reject; their reject is final (`rejected`). So
  open/awaiting_supervisor -> rejected is not allowed.
- **Permissions:** only the person in `assigned_to` can act. It always names whose turn it
  is: the supervisor, then the worker while awaiting_worker, then E201 after a reject.
- **Auto-resolved P2:** stored as `resolved` with `auto_resolved=true`. Sana's duplicate tap
  P0005 is voided in the DB in the same transaction, with audit rows `detected` and
  `auto_resolve`. The scheduled job and undo come in Phase 12.
- **Detection runs on the DB**, so approved fixes show up on the next run. Open
  exceptions that disappear are closed by the system (`no_longer_detected`). Resolved and
  rejected cases are never reopened.
- **Port 5433:** this machine already has a PostgreSQL 18 Windows service on 5432 (that
  service was left untouched).
- **Time:** every business timestamp comes from the fixed demo clock (Thu 16 Apr 08:00);
  log timestamps are real UTC.
- `edit_punches` (P13) has no new times in its engine params, so it can only be applied
  with **edit** and `params.changes`. `request_certificate` is decision-only for now
  (the message to the worker comes in Phase 7).
- A small engine change: P17's "two sites" check ignores correction punches, which are
  typed in by a supervisor rather than punched at a place.

**Notes for later phases**
- **Phase 4:** add fix options for **P3, P4, P6 and P7**. Until then, approve returns 409
  `no_fix_options` for them; they can still be rejected. P2 needs none (auto-resolve).
- **Phase 22:** `POST /api/seed` wipes every table. It must be disabled
  (`ATTENDFLOW_ENABLE_SEED=false`) or protected on the deployed server.

**How to run and verify** (from the repo root)
```bash
python -m uv sync
docker compose up -d db                    # PostgreSQL on localhost:5433
python -m uv run alembic upgrade head      # create the tables
python -m uv run attendflow-api            # open http://localhost:8000/docs
python -m uv run pytest                    # expect 262 passed
```
Done-when check in `/docs`:
1. The page lists 12 endpoints.
2. `POST /api/seed`, then `POST /api/detection/run`: expect `found 17, created 17,
   auto_resolved 1`.
3. `GET /api/exceptions`: 16 `open` and 1 `resolved` (Sana's P2, `auto_resolved: true`).
4. Approve `P1-E001-2026-04-14` with header `X-Actor-Id: E101` and body
   `{"option_id": "set_clock_out_to_scheduled_end"}`. The status becomes `resolved` and the
   audit trail ends with `approve`.
5. Reject `P3-E002-2026-04-13` as E101 with a reason. It becomes `escalated` and is
   assigned to E201.

**Next: Phase 4**
- Read-only tools for the agent, plus fix options for P3, P4, P6 and P7.

## Phase 4: Read-only agent tools + fix options for P3, P4, P6, P7 (2026-11-19) ✅

**Built**
- **Fix options** (engine code, no LLM). Every option now also has `description`,
  `decision_only`, `policy_id` and `requires_worker_confirmation`. `decision_only` and the
  default description come from one table (`ACTION_INFO`), so they always match the writer.
  - P3: `approve_overtime` (decision) and `correct_clock_out` (voids the wrong clock-out and
    adds the confirmed one; prefilled at the 9 h limit, Meena Mon 16:29:47 = 16:30).
  - P4: `record_break` (adds break punches; Neha 12:00-12:30 suggested) and
    `record_missed_break` (decision, follow-up note required).
  - P6: `record_short_rest` (decision, reason required) and `move_next_shift_later`
    (upcoming shift only: previous end + 11 h, rounded up to the minute, same length).
  - P7 (late and early): `accept_reason` (reason required) and `record_as_late` /
    `record_as_early_leave`. Both decision-only.
- Three new writers in `fixes/apply.py` (`correct_clock_out`, `add_break`, `move_shift`),
  with the same one-transaction rule and stale/future/overlap guards.
- **Worker-confirmation guard:** options flagged `requires_worker_confirmation` (P3
  correction, P4 break) are refused (409 `worker_not_confirmed`) until the worker's latest
  reply on the case is Yes.
- **Detection** adds options to cases already in progress that were stored without any
  (audit row `options_added`); status and assignee are untouched. `GET /api/exceptions`
  shows the new fields, and derives them for options stored before this phase.
- **Tools** (`backend/attendflow/tools/`): `get_schedule`, `get_leave`,
  `get_leave_balance`, `get_punches`, `get_policy`, `run_checks`.
  - Typed Pydantic input and output, one-line LLM descriptions, short output (tested
    budgets: 1,000 chars; `get_policy` 2,000 because it returns the real policy text;
    `run_checks` 1,200).
  - Bad input never raises: `{"ok": false, "error": {code, message, hint}}`.
  - `run_checks` applies the change to an in-memory copy, re-runs the whole engine and
    returns new violations, resolved ones, still-open ones, the day's hours and the week's
    projected hours.
- **Registry:** `openai_tools()` gives the OpenAI function-calling list, with schemas made
  from the Pydantic models and flattened (no `$ref`).
- **Read-only, three layers:** tools never get a session (the runner loads the data in a
  `SET TRANSACTION READ ONLY` session that always rolls back), a flush guard, and tests
  (every table snapshotted around every tool; no writer imports in `tools/`).
- **Logging hook:** `ToolRunner(..., on_call=...)` gets name, arguments, output, ok and
  duration for every call. Phase 5 will write `tool_calls` from it.
- CLI `attendflow-tools` (`list`, `schema`, or any tool; `--csv` reads the CSVs).
- 139 new tests (401 total).

**Decisions** (all 16 defaults accepted)
- Option names follow policy.md: P3 is a punch *correction* (not "cut hours"); P4 and P6
  *record* the breach or the reason rather than "approve" it.
- **No `mark_gap_as_leave` for P7:** policy.md does not allow it.
- **policy.md change (approved):** P7 allowed fixes now end with "Early leave beyond grace
  is handled the same way."
- Decision options with a note: an empty note is taken from the approve `reason`; with
  neither, approve is 422 `invalid_params`.
- P3 correction is offered only on single-shift days. The P6 move is never offered if it
  would push the shift onto another date (P15).
- `run_checks` reuses the fix-option `{action, params}` shape (11 actions), so the agent
  can copy an option and change one value. "No violations" = `new_violations` is empty.
  For Amit, a 19:30 clock-out reports **P3 (9.5 h)** and a **new P5 risk (41.5 h)**.
- A parity test approves real fixes on the test DB and checks that detection finds exactly
  what `run_checks` predicted (P1, P5 cut, P3 correction, P4 break).
- Small refactors: `build_context()` in `engine.py`, `week_hours()` out of the P5 check,
  and `shift_end_for_hours()` shared by the writer and the simulation.
- Two Phase 3 tests were updated because their premise changed: "approve without options"
  now empties one stored row by hand, and Karan's P7 now expects the two option IDs.

**Notes for later phases**
- Phase 5: pass `openai_tools()` to the model and run calls through
  `ToolRunner.for_database`; log `tool_calls` from `on_call` in a separate write session.
- Phase 9: P1, P9, P10 and P13 also say "the worker is asked first" but are not flagged
  `requires_worker_confirmation` yet (so the Phase 3 demo approve still works). Decide then.
- Phase 22: `POST /api/seed` must be disabled or protected on the deployed server.

**How to run and verify** (from the repo root; stop a running `attendflow-api`
first, or `uv sync` cannot replace its .exe)
```bash
python -m uv sync
python -m uv run pytest                     # expect 401 passed
python -m uv run attendflow-detect --fixes --policy P3,P4,P7
python -m uv run attendflow-tools get_punches employee_id=E001 date=2026-04-14
python -m uv run attendflow-tools get_leave_balance employee_id=E007 leave_type=sick
python -m uv run attendflow-tools get_policy policy_id=P3
# Git Bash (single quotes keep the JSON intact):
python -m uv run attendflow-tools run_checks '{"employee_id":"E001","date":"2026-04-14","proposed_change":{"action":"set_clock_out","params":{"timestamp":"2026-04-14T19:30"}}}'
```
Done-when check: run_checks prints `2 new violation(s): P5 2026-04-13, P3 2026-04-14`
(with 18:00 instead: `no new violations; resolves P1`). In `/docs`: `POST /api/seed`,
`POST /api/detection/run`, then `GET /api/exceptions`: Meena's P3, Neha's P4 and Karan's
P7 show their options. P6 options are tested on synthetic fixtures (no demo case).

**Next: Phase 5**
- LLM client + agent loop: call the tools, log each call, validate the output.

## Phase 5: LLM client and investigation loop (2026-11-19)

- Added native tool calling to the OpenAI-compatible client. It validates assistant
  messages and retries 429/5xx twice with exponential backoff and bounded `Retry-After`.
  Groq GPT-OSS defaults to low reasoning effort with reasoning hidden from replies.
- The investigation reads a stored exception and runs up to five model steps by default.
  It feeds successful and failed tool results back to the model and returns an `AgentRun`
  with a plain final answer or a stop reason.
- Each tool call commits through a separate journal session. Migration
  `0002_agent_tool_calls` adds run and call identifiers, success and duration, and
  supports multiple calls per step. Start and end audit rows identify the run.
- Verified 409 tests on PostgreSQL, including migration-to-model parity, scripted
  tool calling, failed tool calls, early stops, retry delays and source-data invariance.
  Ruff lint, format and demo data validation passed.
- The first live smoke returned HTTP 400. A diagnostic run completed two native
  tools before Groq rejected the `run_checks` call. The tool schema advertised
  RFC 3339 `date-time` where the app accepts a timezone-free local timestamp.
  The single-tool `run_checks` probe reproduced the 400. Omitting reasoning
  effort, using a minimal tool, sending the full tool list, and sending a tool
  result back all worked in isolation.
- Local timestamp and time schemas now use the existing validation patterns.
  The client reports the provider's error message with key and prompt redaction.
- The post-fix smoke for Amit's P1 finished in two steps (run
  `fcfee5a3d21a4f699341dde2cbf3ca19`). `run_checks` simulated an 18:00 clock-out
  and reported that it resolves P1 with no new violations. The model then gave
  its final answer. All six source tables matched their before-run snapshots.
  This run skipped the separate evidence reads requested in the system prompt.

**Next: Phase 6** adds the structured investigation case, fallback and `/investigate`.

### Phase 5 evidence gate

- The system prompt and first user message require `get_schedule`, `get_punches`,
  `get_leave`, and `get_policy` for the case before `run_checks` or a final answer.
  The loop selects the next required read in the native request. It credits only
  successful reads for the case employee, date, and cited policy.
- Premature simulations return a logged `required_tools_missing` tool error.
  `AgentRun.missing_required_tools` and the closing audit row identify missing
  evidence even if a model returns a final answer. The smoke CLI reports it and
  exits unsuccessfully on incomplete evidence.
- Registry tests recursively check every tool schema for unsupported formats,
  including `date-time` and `time`, as well as `$ref`, `$defs`, and
  `discriminator`. The tests specifically cover the timezone-free formats that
  replaced the schema responsible for the Groq `run_checks` rejection.
- All 415 tests passed against PostgreSQL. Ruff lint and format checks passed.
- The single live rerun for Amit's P1 (run `3d1c6be859e640dc862afa34c8d621a0`)
  completed all four reads in order, simulated the 18:00 clock-out, and stopped
  at `final` with no missing tools. All six source tables were unchanged. The
  model's final text incorrectly said no human intervention was needed even
  though P1 calls for worker confirmation and supervisor approval.

## Phase 6: Structured investigations, fallback, and polling (2026-11-19)

- PostgreSQL migration `0003_investigations` adds the current JSONB case and a job
  table. The assigned supervisor or payroll admin can start a job and poll its
  location from the 202 response. The current exception status stays unchanged.
- The code runs the four evidence reads up front. The model reasons over their
  outputs, can simulate a stored option, and returns JSON. The harness verifies
  citations, the option and its parameters, evidence numbers and times, and
  required human review. It copies matching recorded simulation output and
  derives routing in code. Amit's P1 explicitly requires worker confirmation
  followed by supervisor approval.
- Invalid output gets one correction round. Invalid retries, provider failures,
  and exhausted model steps return a deterministic low-confidence template.
  `LLM_INVESTIGATION_BUDGET_SECONDS` defaults to 45; actual durations go in the
  case, job, audit, and operational logs. Expired jobs and jobs interrupted by
  startup recovery are marked failed and store the template. The watchdog runs
  in the single-process API.
- Offline verification covered structured validation and retry, offline templates
  for P1–P17, Meena's stored P5 options, deadline/restart recovery, and an injected
  instruction. 432 PostgreSQL tests passed, the optional real-key test was skipped,
  and Ruff lint and format checks passed.

**Live verification**
- Wrong-key Amit P1 returned a stored fallback in 1.88 s with `who_to_ask=worker`.
- The first real-key Amit job took 4.01 s. All reads and the 18:00 simulation
  succeeded, but the final model call failed. Its persisted audit and job
  record say `llm_error` only. The original error message was unavailable
  because detailed diagnostic reporting was added after that run. The failure
  preceded JSON mode, so there is no evidence that JSON mode caused it.
- After simulation, the final request starts a fresh system/user conversation
  containing the evidence and recorded simulation as data. That request uses
  JSON mode with no tool definitions or native tool-call transcript. The
  server parses the text and verifies the matching persisted simulation.
- The authorized real-key rerun (run `d6ff62d41c004220866454a77a9c5c0e`)
  stored a validated case in 3.23 s with `fallback=false`, next contact
  `worker`, and a successful 18:00 simulation. The read trace confirmed no
  leave and a 09:00–18:00 scheduled shift. The case requires worker confirmation
  and supervisor approval. All six source tables and the exception status
  were unchanged. The rerun used two model calls, with retries disabled for
  verification. Meena was checked offline only.
- 433 tests passed against PostgreSQL, one opt-in live test was skipped, and
  Ruff passed.

**Verify:** migrate to head, start the API, POST `/api/exceptions/{id}/investigate`
with `X-Actor-Id: E101` for an assigned demo case, poll the `Location` using the
same header, then GET the exception detail. To print Amit's template offline:

```bash
python -m uv run attendflow-agent-smoke P1-E001-2026-04-14 --fallback-only
```

**Next: Phase 7** adds the worker message and Amit's view.

## Phase 7: Worker messages and inbox (2026-11-19)

- `ask-worker` checks the stored code-owned route, runs one wording attempt
  using verified facts, and saves the message and source. A model error or
  message validation failure uses the template. The handoff and audit commit
  together and `waiting_since` uses the application clock.
- `GET /api/worker/messages` only returns the actor's own worker-facing
  questions. Yes returns a small receipt and reassigns the exception to the
  supervisor. No requires details, sets `needs_actual_time=true`, and stays
  in the worker inbox, outside the supervisor queue.
- Migration `0004_worker_messages` adds the questions and replies table and
  backfills a template for legacy cases already waiting for a worker.
- Vite and React provide Amit's inbox and the supervisor's `/dev` page.
  The latter polls the investigation job before enabling the handoff. CI
  checks generated OpenAPI types, runs component tests and type-checking,
  and builds the frontend. Review `/dev` in Phases 15 and 22.
- Local verification passed 444 PostgreSQL tests, with one opt-in provider
  test skipped, and five frontend tests. OpenAPI drift, TypeScript,
  Ruff, and the production build passed.

- A mobile Chromium check on an isolated database verified the dev page,
  polling, the wrong-key template, and the No reply through an inbox reload.
  The audit recorded HTTP 401 and a 1.38 s template delivery. The case stayed
  out of Ravi's queue.
- The single authorized real-key request on Amit's P1 used the template after
  the model reply failed validation with `worker message must be short plain
  text`. The message took 2.49 s to generate and is in Amit's dev inbox.
  No retry was made. All six source tables were unchanged.

- The initial real-key audit retained the generic short-plain-text error and
  stored template only. The original reply and its formatting were unavailable,
  so the specific trigger could not be identified. Validation now trims
  whitespace and wrapping quotes and flattens line breaks. The prompt requests
  one or two plain sentences, and date, exact-question, and verified-number
  checks still apply.
- The single real-key follow-up on an isolated copy of Amit's P1 stored an
  LLM-written message in 1.16 s with no diagnostic. The existing dev inbox
  message was preserved. The PostgreSQL suite passed 447 tests, with the
  opt-in provider test skipped. Ruff lint and formatting passed.

**Next: Phase 8** validates the actual time from a No reply before moving the
case to the supervisor.

## Phase 8: Validate and re-check a worker's actual clock-out (2026-11-19)

- Migration `0005_worker_time` records the fix asked about, the worker's pending
  time review, and the full confirmed re-check on the case. It enables manual
  entry for legacy No replies with a supported stored clock-out option.
- P1 missing clock-outs and P3 wrong clock-outs use tool-free JSON extraction.
  Code checks the claimed time against the reply, clock-in, fixed clock, and
  maximum shift length. A single approximate time can become a candidate.
  Unclear times and provider failures expose manual entry. Invalid model
  output gets at most one correction attempt in normal operation.
- The inbox supports Confirm, Edit, and manual time, including on reload.
  The server simulates the proposed change before handoff and builds the
  worker's impact note from the result. Yes runs the same re-check with the
  proposed time captured when the message was sent. P1 approval requires the
  worker-confirmed timestamp and uses it for the stored option. The original
  investigation remains available alongside the subsequent worker re-check.
- The audit records the raw worker reply, extraction or manual result, source,
  and re-check. `LLM_DIAGNOSTICS=on` keeps up to 150 sanitized characters of
  rejected output in demo audits. Set it to `off` in a real deployment
  because worker text is personal data.
- The two isolated real-key checks used one extraction attempt each. The truck
  reply yielded approximate 19:30 with medium confidence. Confirmation stored
  a P3 breach at 9.5 h and a P5 risk at 41.5 h projected, resolved P1 in simulation,
  and assigned the case to the supervisor. "After 7" stored a low-confidence
  clarification with no time or re-check and kept the case with the worker.
  The wrong key returned HTTP 401 and manual 18:00 resolved P1 in simulation
  with no new violations. None of the three runs wrote to the source tables.
- Local checks passed 478 PostgreSQL tests and eight frontend tests. Two
  opt-in provider tests were skipped. Ruff, OpenAPI drift, TypeScript, and the
  production build passed. Hosted CI awaits the Phase 8 push.

**Verify:** migrate to head, start the API and Vite, then use `/dev` to send a
question for a fresh Amit P1 case. Open the inbox, answer No and provide a
clock-out, then confirm or use the manual field. The exception detail contains
the re-check. Repeat with a fresh case and Yes to verify the scheduled time.

**Next: Phase 9** adds Ravi's approval page.

## Phase 9: The supervisor's approval screen (2026-11-19)

**Built**
- `GET /api/supervisor/queue`: the caller's team cases that are `awaiting_supervisor`,
  or `open` with an investigation routed to the supervisor, plus escalated cases
  assigned to the caller. Priya sees only escalated cases assigned to her. Cases still
  waiting for the worker's time (`needs_actual_time`) never appear. Sorted by severity,
  date, ID.
- `GET /api/supervisor/cases/{id}`: the case card for the assignee only. It has the
  issue, policy quote, the worker's own evidence, raw reply, confirmed time (with
  `approximate`), stored re-check, and fix options with edit fields. It also carries a
  consequence note built by code (for example "Approving a 19:30 clock-out makes the
  day 9.5 h, over the 9 h limit (P3) and projects 41.5 h for the week, over 40 h
  (P5)..."). Other workers' IDs and names are redacted. No LLM calls.
- Approve/edit/reject hardened: workers get 403 `supervisor_only` on every supervisor
  endpoint, reject needs 10+ characters, decision notes need 3+, and audit rows hold the
  option with params before and after. After a data-changing fix, detection re-runs
  (own transaction, no duplicates) and returns the worker's new exception IDs.
  `applied_fix.label` names the time actually applied.
- P9 and P13 options now need the worker's confirmation. Three older tests now get a
  worker Yes first.
- Frontend `/supervisor`: queue (loading, empty, error), case card, Approve with a
  confirmation step when the fix creates violations, Edit form (typed inputs, locked
  P1 time, P13 punch-time form), Reject with a required reason, and refusals in plain
  words. The acting reviewer lives in `actors.ts`; `?as=E102`/`?as=E201` works in dev
  builds only.
- Docs: machine-specific paths removed from CLAUDE.md and this log.

**Decisions**
- Detection runs automatically after an approval that changed data. Its failure never
  undoes the approval (`post_fix_detection_failed` in the audit).
- Open cases join the queue only after an investigation routes them to the supervisor.
  Worker-routed cases wait for the worker's reply.
- P10 keeps no worker guard (its policy asks only for supervisor approval).
- A P1 time is locked to what the worker confirmed. P3 corrections stay editable after
  a Yes (Phase 4 behaviour).

**Checks**
- 500 backend tests passed (2 opt-in real-LLM tests skipped), including 22 new
  Phase 9 tests: queue scope and sort, needs_actual_time, card and consequence note,
  redaction, edit/reject/decision-only rules, detection failure, the permission
  matrix, and Amit's story end to end. 23 frontend tests (15 new). Ruff, type-check,
  production build and the OpenAPI drift check passed.
- Live check (dev DB reseeded, no LLM key, so the investigation used the template and
  Amit used the manual time field): Amit answered No with "left around 7:30ish" and
  sent 19:30. Ravi's queue showed the case only after that. The card showed the time,
  his words, the re-check (9.5 h day, 41.5 h week) and the note. Approve asked for
  confirmation, wrote a 19:30 correction punch, and opened P3-E001-2026-04-14 and
  P5-E001-2026-04-13 for Ravi. The audit ran from detected to post_fix_detection.
  Sunita got 403 on the card. Ravi rejected Meena's P5 from the UI. It landed
  escalated for E201 with the reason saved, appeared on `/supervisor?as=E201`, and
  Ravi then got 403. Two display bugs found here were fixed and tested.

**Phase 22 checklist (deployment)**
- Disable or protect `POST /api/seed`.
- Review or remove the `/dev` page.
- Confirm the dev-only `?as=` reviewer override is absent from the deployed bundle.
- Replace `X-Actor-Id` with real login.

**Verify:** start the DB, `alembic upgrade head`, `attendflow-api`, and `npm run dev`.
Seed, detect, investigate Amit's P1 and ask him on `/dev`. Answer No on `/` and send
19:30. Then open `/supervisor`, check the card, and approve. `GET
/api/exceptions?employee_id=E001` shows the new P3 and P5. Try `/supervisor?as=E102`
(Sunita sees none of Ravi's cases).

**Next: Phase 10** gives Priya her plain list and adds the prototype integration test.

## Phase 10: Priya's list, read-only detail, end-to-end tests (2026-11-19). Prototype complete

**Built**
- `GET /api/admin/exceptions` (payroll admin only, others 403 `admin_only`): every
  exception with employee name and team, policy, severity, status, kind, auto-resolved,
  assignee, summary, whether an investigation exists and its `who_to_ask`, and
  `needs_your_decision` (escalated to the caller). Filters: status, policy, team, employee,
  severity, `q` (name or ID, wildcards treated as text). Sort: severity, then date (default),
  or date, employee, updated. `limit` (default 200, max 500) + `offset`, `matched` total.
  The same response carries the counters (total, the six statuses, auto_resolved), counted
  by the database over all rows, and the filter choices.
- `GET /api/admin/exceptions/{id}`: read-only. Issue, cited policy, full evidence (not
  redacted for payroll), fix options with the Phase 9 consequence note, the stored
  investigation, the latest job, every worker message and reply, the stored re-check, the
  applied fix, the full audit trail oldest first (actor name, a code-built summary,
  reason, status/assignee before and after), and tool calls (arguments and outcome only:
  no tool output, prompts or keys). No LLM calls.
- `/admin` page: counter cards (click to filter), filters and a debounced name search,
  table with status and severity badges and a "Needs your decision" marker, loading/empty/
  error states, and a detail panel with an **Investigate** button (reuses the investigate
  job and polling). Escalated cases assigned to Priya embed the Phase 9 decision card
  (`CaseCard`, now exported and taking an `actor`).
- `adminActor` in `actors.ts` (E201; `?as=` in dev builds only). The shared API calls
  take an optional actor.
- `docs/DEMO_WALKTHROUGH.md`: the click-by-click prototype demo with numbers from a live
  run.

**Decisions** (all defaults accepted)
- Counters ride in the overview response and ignore filters. Search is server-side.
- Priya only investigates from her page. Ask-worker stays with the assigned supervisor.
- Acting on an escalated case reuses the supervisor card inside `/admin`. A link to
  `/supervisor` would have needed the dev-only `?as=E201`.
- The older open endpoints (`GET /api/exceptions`, `/api/audit-log`, `/api/tool-calls`)
  stay unscoped for `/dev`. They go on the Phase 22 list.
- No Playwright. The walkthrough doc plus the live check cover the browser path.

**Checks**
- 527 backend tests passed (2 opt-in real-LLM tests skipped; 27 new).
- New backend tests: `test_admin.py` (21: permissions, counters equal raw SQL counts,
  every filter, sort and paging, auto-resolved marks, escalation marker, detail audit
  order and re-check, no key/prompt/tool output, investigate reuses the running job and
  returns 202) and `test_e2e_prototype.py` (6). The e2e tests use the HTTP API only:
  1. Amit's main story with scripted models at all three LLM steps. It asserts the exact
     audit sequence, the correction punch, the new P3/P5, and Priya's counters before and
     after.
  2. The reject path, ending in Priya's final reject.
  3. The LLM down / invalid at every step (2 runs). The template investigation, template
     message and manual time are used, and the audit names each failure.
  4. A data-safety test: a SQL hook records every write to timecards, schedule and leave
     with the code that caused it. Only `fixes/apply.py` and the seed write, and every fix
     write matches an approve/auto_resolve audit row that lists the change.
  5. A test that this hook flags a rogue write.
- Frontend: 33 tests (10 new: admin page counters, filters, search, empty/error/loading,
  detail, investigate polling, escalated card as E201; admin actor). Four supervisor
  tests now also assert the acting reviewer.
- Ruff, type-check, production build and OpenAPI drift check pass. The production bundle
  contains no `URLSearchParams` (the admin query string is built by hand to keep that
  Phase 22 check meaningful).
- Live check (dev DB reseeded, no LLM key): 17 found, 16 open, 1 auto-resolved. Amit's P1
  went through investigate, ask, No + "7:30ish", manual 19:30 (9.5 h day, 41.5 h week),
  and Ravi's approval, which opened P5-E001-2026-04-13 and P3-E001-2026-04-14 (19 all,
  17 open, 2 resolved). Priya investigated Meena's P5 from `/admin`, Ravi rejected it
  (then got 403), and Priya's reject made it final (16 open, 1 rejected, 0 escalated).
  Two display fixes came from this check: model-failure audit rows now quote the stored
  cause, and the page no longer labels a non-admin as "payroll admin".

**Phase 22 checklist (added)**
- Restrict `GET /api/exceptions`, `/api/audit-log` and `/api/tool-calls` to the payroll
  admin (or remove them with `/dev`).

**Verify:** start the DB, API and Vite, reseed and detect, then follow
`docs/DEMO_WALKTHROUGH.md`. `python -m uv run pytest tests/test_e2e_prototype.py -v` runs
the three end-to-end stories without a key.

**Next: Phase 11** (mock punch API + scheduler) starts the full product.

## Phase 11: Mock attendance device and scheduler (2026-11-19)

**Built**
- `POST /api/punches`, a mock attendance device authenticated by `X-Device-Key`
  (`DEVICE_API_KEY`; without a key configured it answers 503). It accepts in/out/break
  punches in local time. It refuses an unknown or non-worker employee, a time after the
  as-of time or more than 7 days before it, an unknown location, an exact duplicate and
  bad input, always in the shared error shape (401/409/422/503).
- `ingest/punches.py`, the one new writer of source data. It only inserts timecards rows,
  and each punch gets a `punch_ingested` audit row (actor `device`) in the same
  transaction. It shares the punch ID lock with `fixes/apply.py`.
- Detection after a punch (`detect_after_punch`) runs for that worker's Mon-Sun week in
  its own transaction. If it fails, the punch stays and the failure is audited.
- A scheduler: a background thread in the API with a non-overlap lock. Each cycle runs
  detection for everyone, investigates new open cases (newest first, one at a time, per
  cycle limit), sends worker messages for cases routed to the worker (acting as
  `system`), and stores a summary in `scheduler_runs` plus a `scheduler_cycle` audit row.
  One failing case is recorded and the cycle continues.
- Endpoints for Priya only: `GET /api/admin/scheduler`, `POST .../run-now`,
  `.../start`, `.../stop`. With `ATTENDFLOW_DEMO_MODE=true` only:
  `POST /api/admin/demo/reset` and `POST /api/admin/demo/punch`.
- Migration `0006_device_and_scheduler`: `device` audit actor, `scheduler_runs`,
  `exceptions.investigated_facts_hash`.
- `/admin`: a scheduler status line and **Run scheduler now**. In demo mode it also shows
  a **Simulate punch** form, and the list refreshes itself every 4 s while that form is
  open. The worker inbox takes a dev-only `?as=E004`.
- Plain-language audit summaries for the automatic steps. `ATTENDFLOW_CORS_ORIGINS`
  setting (needed to run a second dev stack on other ports).

**Decisions** (13 defaults accepted, with one change)
- **Backlog (your change):** the scheduler only touches cases first detected after it
  started, after a demo reset, or after the first cycle. Older cases are counted as
  `skipped_backlog`. `SCHEDULER_BACKLOG=true` processes them. Amit's planted P1 stays
  free for the manual walkthrough.
- Investigate again only if the case is open and its engine facts changed (hash stored
  at investigation time). A template result with unchanged facts is never retried
  automatically.
- Worker messages are sent automatically (they change no timecard data) and audited as
  `system`.
- Demo punch is **08:58**, not 09:02: 09:02 is 2 minutes late, so detection would also
  add an auto-resolved P7 (existing within-grace behaviour).
- A demo reset checks the caller against the stored employees. On an empty database, run
  `POST /api/seed` once.
- OpenAPI types are generated with demo mode on, so CI does not depend on `.env`.

**Checks**
- Backend with `REQUIRE_DB=1`: 577 passed, 2 skipped (the opt-in real-LLM tests). 50 new
  test cases: `test_ingest.py` (26), `test_scheduler.py` (22),
  `test_e2e_scheduler.py` (2). Updated: the static writer test allows exactly the ingest
  module (PunchRow, insert only). The SQL write-hook test allows writer `ingest` only as
  an INSERT into timecards, with one matching `punch_ingested` row per new punch. The
  endpoint list includes the new routes and no demo routes.
- Frontend: 51 tests (18 new), type-check, build, OpenAPI drift check. The production
  bundle has no `URLSearchParams` and no `Neha`. One existing admin test now waits for
  the reload effect (it was racy under load).
- Migration 0006 downgrades and upgrades cleanly. Ruff and `attendflow-validate` pass.

**Live check** (dev DB, API on :8011 and Vite on :5183, scheduler every 15 s, 1
investigation and 1 message per cycle)
- No key: demo reset (17 found), then the Simulate punch form sent Neha's 08:58 clock-in
  (P0073). New `P1-E004-2026-04-15`, P10 closed, counters 18 / 16 open. The next timed
  cycle (no click) stored the template investigation in 161 ms (LLM_API_KEY not set) and
  sent the template message. Counters: 15 open, 1 waiting for worker. Neha's inbox
  (`/?as=E004`) showed the question. The audit trail shows detected, auto investigation
  started/finished, ask_worker (system) and message sent. Amit's P1 and inbox stayed
  untouched.
- Real key, one cycle: validated (not template) investigation in 5.65 s, LLM-written
  message in 1.34 s, cycle 7.1 s. The next cycle made no model calls. The real-key API
  was then stopped.

**Phase 22 checklist (added)**: demo mode off, the worker `?as=` override, a strong
`DEVICE_API_KEY` and CORS origins, one API process for the scheduler lock (see CLAUDE.md).

**Verify:** `alembic upgrade head`; put `ATTENDFLOW_DEMO_MODE=true`, `SCHEDULER_ENABLED=true`,
`SCHEDULER_INTERVAL_SECONDS=15` in `.env`; start the API and Vite; open `/admin`. If the
database is empty, run `POST /api/seed` once, then reset with
`POST /api/admin/demo/reset` (header `X-Actor-Id: E201`). Send Neha (E004), Clock in,
2026-04-15 08:58. Within one interval her new P1 shows "investigated → worker", and
`/?as=E004` shows the question. Without a key the same flow uses templates.

**Next: Phase 12** (auto-resolve + undo).

## Phase 12: Auto-resolve with undo, and the "resolved without a human" metric (2026-11-19)

**What existed before** (built on, not duplicated): `policy.json` already had
`auto_resolve: true` on P2 and P7 only. The engine marked P2 duplicate runs and P7
clock-ins within grace as `auto_resolved`, and detection closed *new* rows through
`fixes/apply.py` (P2 voids the extra tap, P7 changes nothing) with a `system` audit row.
The gaps: no P17 or chained-tap guard, no "before" values (so no exact undo), no kill
switch, and nothing stopped `auto_resolve: true` on another policy.

**Built**
- `engine/auto_resolve.py`, the last engine step: each P2/P7 candidate gets a code-built
  `basis` (e.g. "2 'in' taps 2 min apart, within the 5 min duplicate window"),
  `eligible` and `held_because`. Held for a person: taps spanning more than the window
  (chained), taps from two devices or locations, a second clock-in, or any punch that P17
  reviews. Policy load fails if `auto_resolve` is on for anything but P2/P7.
- P2 and P7-within-grace carry one human option each, for when a person decides:
  `void_duplicate` (`void_punches`) and the new decision-only `confirm_within_grace`.
- Kill switch `AUTO_RESOLVE_ENABLED` (default true). Off: candidates are stored open
  with an `auto_resolve_held` audit row. Held cases get the same row with the reasons.
- Snapshot: `apply_auto_resolve` stores every changed row in full, before and after,
  plus the other evidence punches as `guarded_rows` (`applied_fix.snapshot_version` 1).
- Undo: `POST /api/exceptions/{id}/undo` (reason of 10+ characters).
  `fixes/apply.py undo_auto_resolve` restores the "before" values only if every stored
  row still matches. The service also refuses if another case's audited fix touched
  this worker's punches on that shift date afterwards. A refusal (409 `undo_conflict` /
  `undo_unavailable`) changes nothing and writes one `undo_refused` audit row. Success:
  the case goes `resolved -> open` (an undo-only transition) with the worker's supervisor,
  `auto_resolved=false`, `auto_resolve_undone_at/by` set (migration `0007`), an
  `auto_resolve_undone` audit row (actor, before/after, reason), then detection re-runs
  if data changed (`post_undo_detection`).
- No loop: only new rows are ever auto-resolved, the stable ID keeps the undone row, and
  `_auto_resolve` refuses a row with `auto_resolve_undone_at`. The scheduler never
  investigates or messages an undone case, even with `SCHEDULER_BACKLOG=true`
  (`skipped_undone` in the cycle summary). The supervisor queue shows undone open cases.
- Metric: `GET /api/admin/metrics/auto-resolve` (payroll admin). X = auto-resolved and
  not undone; Y = exceptions that needed handling = all minus those closed as
  `no_longer_detected`, which are returned as `closed_by_data_change`; percent,
  `undone`, a per-policy breakdown, optional `date_from`/`date_to`. The existing
  Auto-resolved tile reads the same column, so it always equals X.
- Visibility: `cases/auto_fix.py` builds the case's auto-resolve block (state, basis,
  held reasons, the policy.md "Allowed fixes" quote, what changed in plain words, who/when,
  undo reason, `can_undo`). `/admin` shows the metric line with its footnote, "auto" and
  "undone" badges, and the panel with **Undo** in the case detail. `/supervisor` gets
  **Auto-resolved for my team** (`GET /api/supervisor/auto-resolved`). Plain audit
  summaries: auto-resolved, held, undone, undo refused, detection after the undo.

**Decisions** (all recommended defaults, plus your metric change)
- Y excludes cases closed because the data changed (your change). They are shown as a
  footnote ("Not counted: 1 case closed because the data changed").
- P7 after an undo offers only "confirm within grace": policy.md says a clock-in within
  grace "is not counted as late", so there is no "record as late". Reject still escalates.
- A P7 undo restores nothing; it is refused only if the clock-in itself changed. The
  "another fix touched that day" check applies only to undos that restore data (P2).
- Undo permissions: payroll admin any case; a supervisor only workers whose
  `supervisor_id` is them (403 `not_assigned`); workers 403 `supervisor_only`.

**Checks**
- Backend with `REQUIRE_DB=1`: 621 passed, 2 skipped (opt-in real-LLM). 44 new:
  `test_auto_resolve_engine.py` (19: boundaries 5:00/5:01 and 10:00/10:01, limits from
  policy.json, chained taps, two devices/locations, P17 on P2 and P7, two clock-ins,
  policy switched off, policy load guard, only P2/P7 ever) and `test_api_auto_resolve.py`
  (25: exact snapshot, exact restore, no re-auto-resolve, normal flow after undo,
  refusals with nothing written, permissions, metric before/after undo and with the
  Neha 09:02 punch, scheduler skip with backlog on, kill switch, SQL write-hook data
  safety for auto-resolve, undo and re-approve). Updated: one Phase 4 test (P7 within
  grace now has its human option), the endpoint list, and the write hook's fix actions.
  The static writer test is unchanged: only `apply.py` reads/writes punches for this.
- Frontend: 62 tests (11 new in `AutoFix.test.tsx`: metric tile and footnote, kill
  switch, labels, Undo with reason, error state, supervisor list). Type-check, build and
  the OpenAPI drift check pass. The bundle has no `URLSearchParams` and no `Neha`.
- Ruff, `attendflow-validate`, migration 0007 down and up pass.

**Live check** (own database `attendflow_phase12`, API :8012, Vite :5184, demo mode, no
LLM key; the dev DB on :8000 belonged to another session and was not touched)
- Demo reset: 17 found, Sana's P2 auto-resolved with a snapshot. Metric **1 of 17 (5.9%)**.
- Priya undid Sana's P2 in `/admin`: P0005 restored (not voided), case open with Ravi,
  metric **0 of 17**, tile 0.
- Simulate punch Neha 09:02: P0073 stored; new P1 (open) and P7 (auto-resolved, no data
  change); P10 closed. Metric **1 of 18 (5.6%)**, footnote "1 case closed because the data
  changed".
- Ravi undid Neha's P7 from `/supervisor` → "Nothing to restore"; both undone cases in
  his queue. Metric **0 of 18**, 2 undone.
- Amit's P1: open with Ravi, only `detected`, no investigation, empty inbox.

**Phase 22 checklist (added)**: review the `AUTO_RESOLVE_ENABLED` default and which
policies have `auto_resolve: true` in `policy.json`; review the metric's definition
(X, Y, `closed_by_data_change`) before showing it to real users.

**Verify:** `alembic upgrade head`, then follow section 7 of
[DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md).

**Next: Phase 13** (no-reply escalation).
