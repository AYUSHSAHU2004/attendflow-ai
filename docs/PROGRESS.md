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

## Phase 13: No-reply escalation ladder and the demo clock (2026-11-20)

**What existed before** (built on, not duplicated): `awaiting_worker` cases had
`waiting_since` and a `worker_messages` row, but nothing watched the time. The clock was a
`FixedClock` at the as-of time, so no time ever passed. The scheduler (Phase 11), the
status flow, `ask_worker`, the Phase 8 reply flow, the supervisor queue and Priya's views
were all reused.

**Built**
- Clock split (`clock.py`): `now()` stamps rows and drives timeouts; `data_as_of()` is the
  fixed data cut-off for detection, fixes, worker time checks and device punches. Moving
  the demo clock therefore never changes detection (tested: same findings before and
  after). `DemoClock` = as-of + a forward-only offset, demo mode only
  (`GET/POST /api/admin/demo/clock`, payroll admin, max +14 days, audited, stored in
  `settings`, restored after a restart, zeroed by demo reset; 404 with demo mode off).
- The ladder (`cases/no_reply.py` rules, `cases/ladder.py` runner), step 4 of every
  scheduler cycle and of **Run scheduler now** (timer off is fine): reminder at 8 h,
  team supervisor at 24 h (`awaiting_supervisor`, "Neha Gupta has not replied for 24 h."),
  payroll admin 24 h later if the supervisor has not acted (`escalated`). One step per case
  per check, each once per wait, at the limit and never before, row-locked, with `due_at`
  and `fired_at` in the audit. No step calls the LLM, applies a fix or writes source data.
- Migration `0008_no_reply_ladder`: `exceptions.no_reply_stage` + wait/reminder/
  supervisor/admin/late-reply times; `worker_messages.reminded_at`/`reminder_text`.
  Backfills the wait start of cases already waiting.
- Replies: any reply stops the ladder. At stage 2 the worker can still answer: Yes runs
  the Phase 8 re-check and the case stays with the supervisor ("Replied late"); No sends
  it back to the worker for the actual time with a new wait. At stage 3 the question is
  closed (409 `handled_by_payroll`, inbox note "Payroll is handling this now. Please speak
  to your supervisor."). Asking again starts a new wait.
- Decide without the worker: approve/edit `without_worker` (stage 2+, assignee only,
  reason of 10+ characters, explicit `confirm_time_without_worker` tick for any punch
  time). Phase 8 time checks still run; `fixes/apply.py` still writes. Recorded in
  `applied_fix.without_worker` (reason, stage, hours, time, prefilled/edited) and a
  `decided_without_worker` audit row. The worker's inbox shows "Decided without your
  reply" with the reason.
- `POST /api/exceptions/{id}/escalate` (reason 10+): the supervisor sends a case to
  payroll without rejecting it.
- Visibility: inbox reminder and notices; queue badge "no reply · 24 h" / "replied late";
  card note with the three choices; `/admin` stage badge, **Stuck (no reply)** counter and
  filter, step times in the detail, plain audit summaries for every step; demo clock line
  and +1 h / +8 h / +1 day buttons with the hint "Run the scheduler (or wait for the next
  cycle) to apply."

**Decisions** (15 defaults accepted, with your changes)
- **Your change (Q11):** the ladder covers every case waiting for a worker, hand-asked and
  backlog cases included; the Phase 11 watermark does not apply. Undone cases are skipped.
  Seeded cases never fire by themselves because none waits for a worker after a reset.
- **Your change (Q8):** deciding without the worker needs an explicit tick for the time;
  the audit records prefilled or edited. **Small extension:** the tick applies to every
  option that sets a punch time (P1 set_clock_in/out and P3 correct_clock_out), not only
  P1, so no time is ever set silently.
- **Your wording (Q12)** for the reminder template.
- One step per check, never skipping: after a long clock jump the reminder still comes
  first, the supervisor on the next cycle.
- `needs_actual_time` is kept at escalation (so a late time still works); the queue shows
  stage 2+ cases anyway (instead of clearing the flag, as the carry-over note suggested).
- **Policy text change (user-approved):** policy.md P1, P3, P4, P9 and P13 "Allowed fixes"
  end with "If the worker does not reply in time, the supervisor may decide on the
  evidence."

**Checks**
- Backend with `REQUIRE_DB=1`: 660 passed, 2 skipped (opt-in real-LLM). 39 new:
  `test_no_reply.py` (38: boundaries just before/at each limit, each stage once, clock
  jumps, nothing for open/resolved/rejected/escalated/undone, kill switch, seeded cases
  never fire, a hand-asked seeded case escalates, late Yes/No/time, ask again, decide
  without the worker with every refusal, permissions per stage, escalate, stuck counter
  and filter, demo clock 404/403/422/restart/reset, write log: silence writes nothing)
  and `test_e2e_scheduler.py` (1: Neha's silent path over HTTP only, with the SQL
  write-hook data-safety check). The static writer test is unchanged and passes.
- Frontend: 75 tests (13 new: reminders and notices, queue badge, decide-without-worker
  flow, send to payroll, demo clock control, stuck tile and filter). Type-check, build,
  OpenAPI drift check pass; the bundle has no `URLSearchParams` and no `Neha`.
- Ruff, `attendflow-validate`, migration 0008 down and up (also with a waiting case:
  backfill restored its wait start).

**Live check** (own database `attendflow_phase13`, API :8013, Vite :5185, demo mode, no
LLM key, timer off)
- Silent path: reset (17 found), Neha 08:58 punch, run: template investigation and
  question. +8 h, run: reminder in Neha's inbox. +16 h, run: Ravi's queue "NO REPLY · 24
  H". +24 h, run: escalated to Priya, Stuck 1, "Sent to payroll · no reply · 48 h", every
  step "Nothing was changed". Neha's inbox: "With payroll". Priya decided without the reply
  (reason + tick): 18:00 clock-out via `apply.py`, Neha's P3 and P4 opened (9.03 h), inbox
  "Decided without your reply" with the reason.
- Late Yes at stage 2: stays with Ravi, "Replied late", +72 h fires nothing. Late No: back
  to Neha for the time, a new reminder 8 h later, her typed 17:45 returns it to Ravi.
- The API restart restored the clock offset (+96 h). Amit's P1: open with Ravi, only
  `detected`, no messages.
- Found and fixed during the check: checkbox layout on the card; the "ladder stopped" audit
  row now comes after the reply row; summary wording "after the reminder".

**Phase 22 checklist (added)**: with demo mode off the clock stays fixed and no timeout
fires, so decide demo mode vs a real clock; review the N/M/K defaults; the inbox shows the
supervisor's reason to the worker.

**Verify:** `alembic upgrade head`; set `ATTENDFLOW_DEMO_MODE=true` in `.env`; start the
API and Vite; follow section 8 of [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md).

**Next: Phase 14** (Activity Center + autonomy table).

## Phase 14: Activity Center and the Autonomy Table (2026-11-20)

**What existed before** (built on, not duplicated): `audit_log` already recorded every
step with its actor (`system`, `agent`, `device`, `worker`, `supervisor`, `admin`) and
workflow time, including every Phase 12/13 step; `cases/admin.py audit_summary` already
had a plain sentence for most actions; the `/admin` detail already showed the audit trail
and the tool calls. `tool_calls`, `worker_messages`, the ladder columns, `scheduler_runs`
and `investigation_jobs` were left as they are (the last two use real UTC, so the feed
does not mix them in).

**Built**
- **Autonomy Table registry** (`activity/autonomy.py`): 22 action rows + 6 "never" rows.
  Each row: actor type (code / LLM agent / system / device / human), who does it, approval
  needed, reversible, a one-line guardrail, the audit `(action, actor)` pairs it writes,
  and the tests that prove its approval or limit. Includes Phase 12 auto-resolve (code, no
  approval, undoable) and undo (human, supervisor or payroll), each Phase 13 ladder step
  (system, no approval, "changes no data"), decide without the worker and escalate.
- **README "Autonomy and guardrails"** is generated between markers by the new CLI
  `attendflow-autonomy` (`--write-readme`, `--check`; the check also runs in CI).
- **Activity feed** (`activity/feed.py`, `GET /api/activity`): audit rows newest first,
  paged by `before_id` (50 a page, max 200). Each item: workflow time, actor type and name
  (a person, or Rule engine / Scheduler / No-reply ladder / LLM agent / the device ID), a
  fixed-template sentence, the case (policy, date, title, status) and the employee.
  Filters: actor type, autonomous/human, policy, employee, case, date range.
- **Summary strip** (`GET /api/activity/summary`): investigated, messages, reminders,
  auto-resolved (+ undone), escalated by silence, approvals (+ without the worker),
  rejections, device punches; counted by the database with the feed's scope and filters.
- **Who sees what, in the API:** Priya everything; a supervisor only cases whose worker
  reports to them (no rows without a case); workers 403. `GET /api/autonomy` for
  supervisors and Priya.
- **Case links:** Priya opens the existing `/admin` detail (tool calls now also show a
  code-built `result_summary`). A supervisor opens the existing case card, now readable
  read-only for any own-team case (`can_decide: false`, decision buttons hidden) with a
  compact **How it was checked** trace. Decisions still need the assignee.
- **Frontend** `/activity` (`ActivityPage.tsx`): summary strip, filters, feed with "Load
  older", case detail beside it, **Autonomy** tab with the "Never allowed" list; links from
  `/admin` and `/supervisor`. Works at phone width (no horizontal scroll at 375 px).

**Anti-drift tests** (the harness part)
- Static: an AST scan of the backend finds every audit write (including names resolved
  from local assignments and f-strings over a `Literal` parameter) and fails if an action
  is missing from the registry, or if the registry lists an action no code writes.
- Runtime: a session-wide SQLAlchemy listener (`tests/audit_guard.py`) fails any test that
  writes an `(action, actor)` pair no row covers (self-tested).
- Approval rows: each names existing tests, and each named test must contain a refusal or
  data-safety assertion (`assert_error`, 403/404/409, `snapshot`, `write_log`,
  `pytest.raises`). I also checked every named test by hand: all assert the refusal.
- Autonomous rows: every action happens with its actor in the end-to-end story
  (`tests/activity_story.py`), or names the existing test that produces it (detection
  failures, held auto-resolve, the legacy loop).
- README copy equals the registry's output.

**Decisions** (all 16 defaults, with your two additions)
- **Your addition (Q5):** the leak test runs the story with `LLM_DIAGNOSTICS` on, a
  failing model, a bad draft and a rejected extraction, checks the planted diagnostic and
  preview text is really in the audit log, then scans every feed page (Priya, Ravi,
  Sunita), the summary, the autonomy table and the case cards: no diagnostic, preview,
  before/after, device key or prompt text.
- **Your addition (Q11):** see the approval-row check above.
- Small code change for the scan: `detect_after_fix(after: Literal["fix", "undo"])`.
- Two tests changed because their premise changed (agreed in Q14): Ravi may now read his
  team's escalated case card (`can_decide` false); every decision is still 403.
- `scheduler_cycle` heartbeat rows are hidden from the feed (Q4; the scheduler panel
  shows them).
- **The 08:00 tool-call gap (item 5):** not reproducible through the API. A new test
  moves the demo clock, investigates, and finds tool-call and agent rows at the moved
  time. Only the standalone `attendflow-agent-smoke` CLI (`agent/loop.py`) still uses the
  fixed as-of clock; left as is.

**Checks**
- Backend with `REQUIRE_DB=1`: 700 passed, 2 skipped (opt-in real-LLM). 40 new:
  `test_autonomy.py` (21), `test_activity.py` (15, on the shared story), `test_activity_api.py` (4: empty state,
  failed detection after an undo, the feed never writes, moved clock).
- Frontend: 84 tests (9 new: feed, summary, filters, paging, empty, refusal, case link,
  autonomy tab; read-only card with trace). Type-check, build, OpenAPI drift check pass;
  the bundle has no `URLSearchParams`.
- Ruff, `attendflow-autonomy --check`.

**Live check** (own database `attendflow_phase14`, API :8001, Vite :5174, demo mode)
- Reset, Neha's 08:58 clock-in, run, +8 h run (reminder), +16 h run (Ravi), +24 h run
  (Priya), Ravi undid Sana's auto-resolve. The feed told the story in order with the right
  actors; summary 1/1/1/1 (1 undone)/1/0/0/1. Ravi saw 27 rows, Inbound only, no device or
  clock rows; Neha's escalated card opened read-only with the trace. Amit's P1: open, only
  `detected`.
- **Note:** the run was meant to be offline, but in PowerShell `$env:LLM_API_KEY=''`
  deletes the variable, so the key from `.env` was used: one investigation and one worker
  message went to Groq (demo data only). The launch config now points `LLM_BASE_URL` at an
  unreachable address.
- Found and fixed during the check: "recorded a in" → "recorded a clock-in"; LLM rows
  named "LLM agent"; feed rows stack when a case is open beside them.

**Phase 22 checklist (added):** the new endpoints trust `X-Actor-Id`; the feed shows typed
reasons and a worker's "No" text to payroll and the team's supervisor; supervisors can now
read their team's case cards.

**Verify:** `python -m uv run pytest tests/test_autonomy.py tests/test_activity.py
tests/test_activity_api.py`; `python -m uv run attendflow-autonomy --check`; then section 9
of [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md).

**Next: Phase 15** (role switcher + Priya dashboard).

## Phase 15: Operations dashboard (2026-11-20)

**Built**
- `GET /api/dashboard` reads a consistent PostgreSQL snapshot in a read-only transaction.
  Priya sees all teams, supervisors see their own team, and workers get 403. From and To
  filter inclusive exception dates. The existing admin counters and Phase 12 metric
  supply the matching current-state numbers. Activity continues to count recorded events.
- The page shows active cases by severity, status and policy, the four no-reply stages,
  case and waiting age buckets, workload by the worker's supervisor, P5 weekly hours, and
  the auto-resolve metric. No schema change, audit action, model call or pay calculation.
- The P5 panel calls the engine's existing weekly hours helper at the data cutoff.
  `OVERTIME_WARNING_MARGIN_HOURS` defaults to 4, must be positive and finite, and is
  included in `.env.example` and the Phase 22 checklist.
- The existing admin and supervisor pages link to the dashboard. Priya's drill-down
  links open matching case filters, with the selected dates where applicable. The
  supervisor dashboard links back to its decision queue. This phase retains the
  existing demo identities. Charts use labeled HTML and CSS with no chart dependency.

**Checks**
- Passed a standalone TypeScript check of application sources and built an offline
  esbuild bundle against the cached React packages. Compared with the previous commit
  using the same bundler, the change adds approximately 2.7 KB gzip total (2.3 KB
  JavaScript and 0.4 KB CSS). The output contains no `URLSearchParams` reference.
- Python syntax, seeded engine hours, warning-margin validation, the static source-data
  writer and audit action checks, and the README Autonomy Table check passed.
- Added backend coverage for exact admin filter counts, activity event consistency,
  permissions, date bounds, punch and ladder transitions, undo, read-only SQL, and
  changes to the policy limit and warning margin. Added component coverage for panels,
  loading, empty and error states, and date-aware drill-down links.
- **Verified, CI green.** The project owner ran the full suite with `REQUIRE_DB=1`
  (709 passed, 2 skipped), the frontend checks, and the live desktop and phone checks.
  The owner corrected an E501 violation and Ruff formatting in five files. Always run
  both `ruff check .` and `ruff format --check .` before finishing a phase.

**Verify:** With the API stopped, run `REQUIRE_DB=1 uv run pytest` and
`uv run attendflow-autonomy --check`. From `frontend/`, run `npm run api:generate`,
`npm run api:check`, `npm test`, `npm run typecheck`, and `npm run build`. Then follow
section 10 of [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) on an isolated demo database.

**Next:** Phase 16 (payroll readiness).

## Phase 16: Payroll readiness and human sign-off (2026-11-20)

- Added deterministic Monday–Sunday readiness for Priya and team-scoped, read-only
  supervisors. The report uses the shared case counts and engine hours, links blockers
  and notes to stored case IDs, and identifies the next owner. It catches source
  defects even when detection has not yet stored a case. Standalone pending leave
  needs the existing leave workflow or an isolated test fixture.
- Only a payroll admin can sign a closed, blocker-free week with data. A reason is
  required to reopen. Migration `0009_payroll_signoffs` stores the reviewed snapshot
  fingerprint; a relevant later change flags the sign-off as out of date. The admin
  Activity Center retains both actions. No LLM, pay calculation, override, or export.
- Optional `ATTENDFLOW_DEMO_EXTRA_WEEK=true` adds complete attendance for 6–12 April
  through seed/reset. With it off, seed data and counts are unchanged. The engine
  check with it on returned the exact same 17 findings. The current demo week stays
  in progress when the workflow clock moves.
- Added `scripts/check-all.sh`. It runs the requested backend checks and stops at the
  first failure. Unlike CI, it runs API generation and refuses unexpected drift
  before checking the generated file, and runs frontend tests before type-check.
- **Verified, CI green.** The project owner ran `./scripts/check-all.sh`: 735 backend
  tests passed, 2 skipped, and 93 frontend tests passed, with type-check and build.
  The migration round trip and live payroll page check also passed.
- Both earlier failures are fixed. The payroll test reads the top-level
  `messages_sent` field from the scheduler response. The dataset reader uses
  `session.scalars()` with the same filters and passes the original read-only guard.
- See section 11 of [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) for the in-progress refusal
  and earlier-week sign-off and reopening. Phase 16.5 follows before Phase 17.

## Phase 16.5: Rough deploy

- Added a single-process deployment launcher and same-origin production frontend,
  read-only `/healthz`, shared-password protection, and startup checks for safe
  deployment settings. Managed Postgres URLs normalize to psycopg before migrations.
- Added a multi-stage Dockerfile, a Locked Render Blueprint, and a Koyeb/Neon
  fallback guide. Locked and Guided demo are environment-only profiles. The smoke
  script checks private access, frontend assets, dashboard and inbox, then runs a
  model-free scheduler cycle. Seed and reset require explicit opt-in.
- **Verified locally:** `./scripts/check-all.sh` on a new PostgreSQL test DB.
  758 backend tests passed, 2 skipped. Both Ruff checks, demo-data validation, the
  autonomy and data-safety checks, OpenAPI drift check, 93 frontend tests, type-check,
  and build passed. The bundle passed the dev override, demo name, localhost URL and
  synthetic secret checks. The native launcher migrated a separate local PostgreSQL
  DB and passed locked and guided HTTP smoke checks with no LLM key. Guided reset
  produced the ready closed payroll week. The temporary databases were removed.
- **Pending:** the Docker image build/container runtime, applying the Blueprint
  on Render, host cold-start behavior, runtime Groq connectivity, and a live hosted
  smoke run. The owner has exact Mac build/run and hosted setup steps in
  [DEPLOY.md](DEPLOY.md). No public deployment was made.
- **Update (2026-11-20, owner report):** the Docker image was built and run on the
  owner's Mac and all 4 smoke checks passed; CI is green (run #21). Phase 16.5 is done
  locally. **Render deploy pending:** the repo owner will apply the Blueprint later.
  Nothing is deployed yet; host cold start, runtime Groq connectivity and a hosted smoke
  run remain unverified (tracked on the Phase 22 checklist).
- **Phase 22:** jury actor switching remains an open decision. Production keeps
  the dev-only actor override out of the bundle.

## Phase 17: Daily briefing, worker history and the phone-first inbox (2026-11-20)

**Built**
- **Facts packet** (`briefing/facts.py`), built by code and scoped first: Priya gets all
  teams, a supervisor only their team. It reuses the admin counters, the dashboard
  (workload, P5 overtime, auto-resolve metric), payroll readiness (current-week blockers),
  the activity summary (workflow date) and the decision queue. It holds case IDs, IDs,
  in-scope names, policy titles, dates and numbers only. No free text, prompts, diagnostics
  or secrets.
- **Grounding validator** (`briefing/validate.py`): checks case IDs (exist, in scope, in the
  bullet's section, listed), employee and policy IDs, numbers (packet values, list lengths,
  parts of packet dates, number words), out-of-scope names, unknown proper nouns, future
  tense and promises, action claims the packet does not show, and approval bypass. Failure
  messages are code-built and never quote model text. A deterministic **template** is built
  from the same packet and passes the same checks.
- **Generator** (`briefing/generate.py`): one tool-free JSON call. The shape is in the
  prompt, with no schema object, `$ref`, `$defs` or date-time format. **Your change:** one
  correction request only after a failed check, so at most 2 calls. A provider error or
  timeout goes straight to the template. **Your addition:** the prompt asks for present and
  past tense only, numbers and IDs from the facts only, and cases referred to by ID.
- **Service and API** (`briefing/service.py`):
  - `GET /api/briefing` makes no LLM call and no write. It returns the stored briefing, or
    a template with `stale` when the facts changed.
  - `POST /api/briefing/refresh` refuses with 429 within 5 minutes per scope or after
    40 calls a day, and 409 while busy.
  - The `briefings` table (migration `0010`) stores each briefing with its facts hash.
  - Scheduler step 5 writes Priya's briefing once per workflow day. It runs only after new
    activity since the watermark and only when the facts changed.
- **Audit and autonomy:** `briefing_refresh_requested` (human), `briefing_generated`
  (agent) and `briefing_fallback` (system, reason code only) are registered rows. The README
  table is regenerated, and only Priya sees these rows in the feed. No new writer of
  timecards, schedule or leave.
- **Summaries** (agreed): one grounded team line per team in the same LLM call. The worker
  history shows a code-built outcome per case.
- **Worker history:** `GET /api/worker/history` is worker-only and covers own cases. It
  shows questions, the worker's own answers and a plain outcome. Only the
  decided-without-reply reason is shown, never a reject reason.
- **Frontend:**
  - `BriefingCard` on `/admin` and `/supervisor` shows a label, clickable case IDs and
    Refresh. It refreshes once by itself when stale and reloads after a busy reply.
  - The worker inbox is rebuilt phone first: greeting, Questions / My history switch,
    one question per card, 56 px Yes/No, a focused confirmation ("One more step" when a
    time is still needed), Check again and dark mode.

**Decisions:** all recommended defaults, plus your change (retry only on a failed check)
and your two additions. My own calls:
- JSON or shape errors count as failed checks, so they get the correction.
- The "today" activity counts use the workflow date, matching the activity summary.
- An explicit Refresh always calls the LLM, even with unchanged facts (a person asked).
- The admin and supervisor pages have no dark mode, so the card has none.
- Supervisors do not see briefing rows in their feed (they have no case).

**Checks (run here)**
- Backend `REQUIRE_DB=1 pytest`: 818 passed, 2 skipped. 64 new tests:
  - `test_briefing_validate.py`: 35
  - `test_briefing_api.py`: 19
  - `test_worker_history.py`: 5

  Existing tests updated: the endpoint list, autonomy coverage and the stub in the page
  tests. After later formatting-only edits, the briefing, history, activity and autonomy
  files were rerun: 99 passed.
- `ruff check .` and `ruff format --check .` pass, as do `attendflow-validate` and
  `attendflow-autonomy --check`. Migration 0010 passed downgrade and upgrade.
- Frontend: 108 tests pass (16 new), along with type-check, build, `api:generate` (no
  drift) and `api:check`. The bundle has no `URLSearchParams` and no `Neha`.
- `scripts/check-all.sh` was not run as a script here (`uv` is not on PATH). Each of its
  steps was run with `python -m uv`.

**Live check** (`attendflow_phase17`, API :8017, Vite :5187)
- Offline: Priya's and Ravi's template briefings showed. Ravi's covered Inbound only. A
  case ID opened the detail panel.
- Amit at 375 px, dark and light: Ravi asked him (a human action), and he answered No with
  his own words. He then got "One more step", entered 18:30, saw the confirmation and
  history, and had no horizontal scroll.
- One real refresh with the `.env` key passed every check on the first draft: 1 call,
  2.6 s model latency, 3.0 s end to end.
- The real draft said P3-E002 is "awaiting supervisor review" (it is open) and that
  Outbound has "no pending items" (it has 5 active). The validator does not check status
  words; I did not loosen or change it.
- Amit's P1 had only `detected` until Ravi acted. No briefing row touches it.
- Found and fixed during the check:
  - The card stayed stale after a 409 from a second tab; it now reloads.
  - Case links now scroll to the detail panel.
  - The Vite launch command did not take the port in PowerShell.

**Render deploy pending** (Phase 16.5, see above). Nothing is deployed.

**Follow-up: status and emptiness checks** (user request after the first real run)
- `status_mismatch`: a status phrase tied to a case ID must match that case's status in the
  packet. The phrase belongs to the nearest group of IDs in its sentence ("A and B
  awaiting supervisor" covers both), "open" fits any active status, and negated phrases are
  not checked. Message example: "P3-E002-2026-04-13 is open, not awaiting supervisor".
- `false_empty_claim`: "no pending", "nothing waiting", "no open cases", "all clear" (and
  close variants) for the headline, a section or a team whose count is above 0.
- Both use the one correction request; messages are code-built. No other check changed.
- Tests: 18 new in `test_briefing_validate.py` (53 there now), including both real
  examples as regression tests, correct wording that must pass, and a correction run.
  Rerun: validator, briefing API, activity and autonomy tests, 112 passed. Both ruff
  checks pass.
- Second real-key refresh: the first draft passed every check (including the new ones), so
  there was no retry. 1 call, 2.4 s model latency, 2.8 s end to end. Its only status
  phrase about a case ("P5-E002-2026-04-13 remains open") is true.

**Status (owner report):** committed and pushed as `e9e4a7b`. Verified with
`./scripts/check-all.sh` on the Windows PC: 836 backend tests passed, 2 skipped; 108
frontend tests passed. **CI: green.**

**Next:** Phase 18 (settings backend).

## Phase 18: Runtime settings backend (2026-11-20)

**What existed before** (built on, not duplicated): the `settings` table (demo clock,
scheduler watermark), the frozen `Settings` with its start-up checks, `require_admin`, the
audit log, the Autonomy Table and its anti-drift tests, the static writer test and the SQL
write hook.

**Built**
- `runtime_settings.py`: a whitelist of ten settings with fixed bounds, strict JSON types
  and plain-words 422s. Effective value = runtime override (one `settings` row,
  `runtime_overrides`) > the server value (env/.env) > the code default, with `source`
  reported. Five more settings are shown read-only. Every other Settings field and any
  policy key is 403 `setting_locked`.
- API (payroll admin only): `GET /api/settings`, `PUT /api/settings/{key}`,
  `POST /api/settings/{key}/reset`, `GET /api/settings/history`. A reason of 10+
  characters on every change and reset; `confirm: true` to turn auto-resolve on; 409
  `no_change` / `no_override`; the cross-setting rules (reminder before supervisor, margin
  below the P5 limit) are checked in plain words before the start-up checks.
- No restart: routes read the effective settings per request; the scheduler reads them
  once at the start of each cycle (`CycleDeps.for_cycle()`), so a change made while a cycle
  runs applies from the next one. No cache, so no stale value and no state shared between
  threads; writers lock the overrides row.
- Never retroactive: migration `0011_no_reply_limits` stores the ladder limits on each case
  when its wait starts; waiting cases are backfilled with the env values. Auto-resolve
  only ever touches newly detected cases.
- Audit `settings_changed` / `settings_reset` (actor admin, key + old/new value and source
  + reason, nothing else). Autonomy rows `runtime_settings` and
  `never_runtime_policy_change`; README regenerated. Feed: Priya only, with her reason.
- `/admin`: a read-only **Current settings** panel (value, source badge, range, last change
  and reason). Editing is Phase 19. API types regenerated.

**Decisions** (all 16 defaults, with your two changes)
- **Your change:** lower LLM-cost limits for the Groq free tier: investigations per cycle
  0-5, messages per cycle 0-10, briefing LLM calls per day 0-100.
- **Your change:** the deployed Locked profile refuses PUT and reset for everyone (403
  `settings_locked_in_profile`); GET and the panel still work. Guided and local dev allow
  changes (Priya only). The profile check runs first, so the refusal is the same for
  everyone.
- **Your rule:** no AI attribution in commit messages, code comments or docs (CLAUDE.md
  working rule 9).
- My calls: `source` is `env` only when the server value differs from the code default;
  an env value outside the runtime range is shown with `within_range: false` and reset
  returns to it; a stored override that no longer fits (after an env change) is skipped
  and logged; CORS now allows PUT (for Phase 19).

**Checks (run on the Mac with the project `.venv`; `uv` is not installed here)**
- Backend with `REQUIRE_DB=1` (one pytest run, no API running): **907 passed, 2 skipped**
  (the opt-in real-LLM tests); 909 collected. New: `tests/test_runtime_settings.py` (69 with
  parameter cases: permissions, locked keys, bounds and types, cross-setting rules,
  reasons, confirm, no change, reset, history, feed, audit content, Locked and Guided
  profiles, the scheduler cap on the next cycle and a change during a cycle, auto-resolve
  off, ladder limits never re-timed, demo reset, SQL write hook, static module check) plus
  2 new Autonomy-row cases. Two existing tests updated: the endpoint list and the
  dashboard read-only test (the settings SELECT now comes first, then the read-only
  transaction). The leak test caught the word "diagnostics" in my new "never" row on the
  Autonomy tab; I reworded the row and left the test unchanged.
- `ruff check .`, `ruff format --check .`, `attendflow-validate`, `attendflow-autonomy
  --check` (README regenerated).
- Migration 0011: upgrade, downgrade, upgrade on a throwaway DB; the backfill gave a
  waiting case the env limits (reminder 6 h from the env, 24/24 defaults) and left the 16
  others empty.
- Frontend: `api:generate` then `api:check` (no drift), **111 tests passed** (3 new for
  the panel), type-check, build. The bundle has no `URLSearchParams` and no `Neha`.
- Live check (`attendflow_phase18`, API :8018, Vite :5188, Mac launch configs
  `phase18-api-mac` / `phase18-web-mac`, no LLM): seed, detection (17), a real change to
  12 h shows on `/admin` as **Changed at runtime** with Priya's reason; 6 investigations
  per cycle, Ravi, and `llm_model` were refused in plain words. At 375 px the page has no
  horizontal scroll (the table scrolls inside its box); no console errors.
- Not run here: `./scripts/check-all.sh` as one script and the Windows checks.

**Phase 22 checklist (added):** the settings API trusts `X-Actor-Id` (Guided profile:
anyone past the password gate can act as E201); overrides in the DB win over env values
after a restart, so review them before go-live; CORS allows PUT.

**Verify:** `python -m uv run alembic upgrade head`, then `REQUIRE_DB=1 python -m uv run
pytest tests/test_runtime_settings.py` and section 13 of
[DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md).

**Status (owner report):** committed as `c945421`. **CI: green.**

**Next:** Phase 20 (employee Q&A). Phases 19 (admin UI) and 21 (analytics) are skipped on
purpose (owner decision, 2026-11-20); the settings stay read-only on `/admin`.

## Phase 20: Employee Q&A (2026-11-20)

Phases 19 (admin UI) and 21 (analytics) are skipped on purpose (owner decision).

**Built**
- **Ask tab** in Amit's phone inbox (`WorkerAsk.tsx`): a question box with a character
  counter, five suggestion chips, an answer card labelled **AI answer**, **Template answer**
  or **Can't answer**, and source chips. A policy chip opens the policy.md text inline; a
  case chip opens the case in My history when Amit was asked about it, else its summary.
  56 px targets, dark mode, no horizontal scroll at 375 px. Opening the tab reads the
  history only and never calls the LLM.
- **Code first** (`qa/intents.py`): refusals with no LLM call for questions about another
  person, pay or salary, changes ("approve my case"), rule-changing text and other
  languages. Dates come from code only (the first date mentioned wins); the previous and
  current Mon-Sun weeks are answerable, anything else is out of range. Keywords pick from a
  closed list of six intents; the model picks from the same list only when keywords find
  none or more than two, and its reply is checked.
- **Facts packet** (`qa/facts.py`): one READ ONLY transaction through the existing tool
  functions with the asker's ID set by code; at most 3000 characters. P17 cases never
  enter it; a day whose only case is P17 gets a fixed "please ask your supervisor" line.
- **Answer** (`qa/generate.py`, `qa/validate.py`): at most 3 calls (intent only when
  needed, answer, one correction after a failed check). Provider error, HTTP 429 (own
  reason `rate_limited`) or the deadline: template at once. The Phase 17 checks moved to
  `grounding.py` and are shared (no change in the briefing's behaviour; its 53 tests pass).
  Q&A adds checks for pay, other people, leaks, "I changed" claims and sources.
- **Storage and audit:** `worker_questions` (migration `0012`), visible to the asker and
  Priya (`GET /api/admin/worker-questions`). Audit rows `qa_answered` (agent),
  `qa_fallback`, `qa_refused` (system) carry codes and counts, never text. Autonomy rows
  and the never row `never_qa_acts`; README regenerated. Feed: Priya only.
- **Limits:** 300 characters, 10 questions per worker per hour, 60 Q&A calls a day, 15 s
  deadline, per-worker lock. Runtime settings `qa_questions_per_hour` (1-30) and
  `qa_max_llm_calls_per_day` (0-100); `qa_enabled` read-only.
- **Golden set** `tests/qa_golden.json`: 20 questions (12 answers, 8 refusals incl. the P17
  line), run through the template path and a scripted model.

**Decisions:** all 22 recommended defaults, plus your three additions (packet under 3000
characters with 429 as its own provider reason and token usage per call; the own name and
own supervisor never trigger the other-person refusal; the fixed P17 line). My calls:
- A sixth intent, `my_supervisor`, so "Can I ask Ravi about this?" gets a real answer. The
  supervisor may be named only as the person to ask (contact verb, not possessive);
  "Ravi's leave" or "How many sick days does Ravi have?" is refused.
- Policy IDs anywhere in the facts count as grounded (P14's text names P8 and P1).
- An AI answer that cites nothing shows no source chips (no fallback chips under "I can't
  answer that").
- The submit button is "Send" (the tab is "Ask").

**Checks (Mac, project `.venv`; `uv` is not installed here)**
- Backend `REQUIRE_DB=1 pytest` (one run, API stopped): **1052 passed, 2 skipped** (the opt-in real-LLM tests). New:
  `test_qa_api.py` 35, `test_qa_validate.py` 40, `test_qa_intents.py` 66,
  `test_qa_golden.py` 3. Updated: endpoint list, settings list, autonomy coverage map.
- `ruff check .`, `ruff format --check .`, `attendflow-validate`, autonomy `--check`
  (run as `python -m attendflow.scripts.autonomy_cli`; the `.venv` has no
  `attendflow-autonomy` script). Migration 0012 upgrade, downgrade, upgrade.
- Frontend: `api:generate` then `api:check` (no drift), **119 tests passed** (8 new),
  type-check, build. The bundle has no `URLSearchParams` and no `Neha`.
- Live check (`attendflow_phase20`, API :8020, Vite :5190, launch configs
  `phase20-api-mac` / `phase20-web-mac`, unreachable LLM): Ask tab at 375 px in light and
  dark mode, template answer with case and policy chips, refusal card, no horizontal
  scroll, 56 px targets, no console errors from the app.
- Not run here: `./scripts/check-all.sh` as one script and the Windows checks.

**Real-key check** (2 Groq calls, cap set to 2, then 1 approved re-run; key never printed)
- "How many sick days do I have left?": keywords chose `leave_balance` (no intent call);
  the first draft passed every check, no retry; 1 call, 1.02 s model, 1.03 s end to end;
  571 prompt + 61 completion tokens. Answer: "You have 11 sick days left for 2026."
- "Why was my punch on Tuesday flagged, and will it be fixed today?": keywords chose
  `my_cases` + `my_punches` (no intent call); the first draft passed every check; 1 call,
  0.51 s model, 0.53 s end to end; 572 + 52 tokens. The model said it could not answer and
  sent Amit to Ravi Kumar, which was correct for the facts it got: **bug found**, the date
  step took "today" (Thursday) instead of "Tuesday". Fixed (the first date mentioned wins)
  with tests.
- **Re-run after the fix** (owner-approved, exactly 1 Groq call, daily cap set to 1): the
  code chose Tue 14 Apr 2026 and `my_cases` + `my_punches` (keywords, no intent call); the
  facts held P1-E001-2026-04-14 and P14-E001-2026-04-14-P0037 (2008 characters). The first
  draft passed every check, no retry; 1 call, 1.08 s model, 1.10 s end to end; 1014 + 164
  tokens. Answer: the clock-out punch is missing (P1), the case is being reviewed by the
  supervisor and "has not been fixed yet"; no promise. Sources: P1 and the P1 case. It did
  not mention the P14 holiday case (grounded but incomplete; no check required every case
  at the time). Both gaps are fixed in the follow-up below.
- No validation check rejected harmless wording; nothing was loosened.
- **Where the cap was set:** only in the throwaway scripts outside the repo (scratchpad
  `qa_real.py` and `qa_real_one.py`), as an in-memory `replace(settings,
  qa_max_llm_calls_per_day=2 / 1)`. `.env` has no QA_ line and was not touched (last
  changed 19 Nov), no database holds a Q&A override (`attendflow_phase20` has no
  `runtime_overrides` row), and the code default, `.env.example` and docs stay at 60. There
  was nothing to restore.

**Follow-up: status words and day coverage** (user request after the real-model re-run; no
further Groq calls)
- Each case in the facts now carries code-built `status_words` (open = "flagged, not yet
  reviewed", awaiting_supervisor = "with your supervisor for review", awaiting_worker =
  "waiting for your answer", escalated = "with payroll for review", resolved, rejected =
  "closed by payroll with no change to your record"; resolved and rejected cases also keep
  the code-built outcome). The prompt tells the model to reuse that wording and to name
  every case of a one-day question. Case chips show "Status: ..." from the same words.
- New check `status_word_failures`: plain status phrases are checked even without a case
  ID, against the sentence's own case IDs, else every case in the facts. "Reviewed by /
  awaiting / with your supervisor" needs an awaiting_supervisor case, "under review"
  awaiting_supervisor or escalated, "waiting for / needs your answer" awaiting_worker, "is
  resolved / fixed" resolved, "is closed" resolved or rejected, "escalated / with payroll"
  escalated. Negated phrases ("not yet reviewed by your supervisor", "has not been fixed")
  are not claims. Code-built message, e.g. "the answer says a case is with the supervisor,
  but in the facts P1 is flagged, not yet reviewed; P14 is flagged, not yet reviewed".
- New check `incomplete_day`: a one-day question with N > 1 visible cases must cover each
  by case ID or policy ID, else "the answer must cover all 2 items on that day (P1, P14)".
  The P17-only rule is unchanged (P17 is never a visible case). The day template now lists
  every visible case with its status words. Both failures use the one correction request.
- Regression tests with the two real examples (the exact real answer; an answer covering
  only P1), correct wordings that pass (open = "flagged, not yet reviewed"; both cases by
  ID or by policy ID; an awaiting_supervisor case "with your supervisor"), the other status
  phrases, the complete template, the correction path over the API and the fallback after
  two failed drafts. Golden set: the Tuesday answers now cover P1 and P14 with the right
  status, the real Tuesday question is a golden item, and "who-supervisor" was dropped to
  stay at 20 ("ask-ravi" covers that intent). No other check changed.
- Not changed: the worker's My history (Phase 17 `outcome()`) still says "Your supervisor
  is reviewing it." for an open case.
- Checks: `ruff check .`, `ruff format --check .`, autonomy `--check`, `api:check` (no
  OpenAPI drift; no frontend file changed in this step), backend `REQUIRE_DB=1 pytest` (one run, API stopped): **1063 passed, 2 skipped**.
  `test_qa_api.py` now 37, `test_qa_validate.py` 49.

**Phase 22 checklist (added):** the Q&A endpoints trust `X-Actor-Id`; `worker_questions`
holds personal text (proposed retention 90 days, no purge job yet); keep diagnostics off
and set the QA caps for the Groq plan.

**Verify:** `python -m uv run alembic upgrade head`, then `REQUIRE_DB=1 python -m uv run
pytest tests/test_qa_api.py tests/test_qa_golden.py` and section 14 of
[DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md). **CI: pending** (not committed yet).

**Next:** Phase 22 (deployment).
