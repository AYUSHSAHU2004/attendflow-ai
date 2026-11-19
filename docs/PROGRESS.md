# Progress log

Project path: `C:\dev\attendflow-ai`. Repo: https://github.com/AYUSHSAHU2004/attendflow-ai.
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
- **Environment:** the project lives at `C:\dev\attendflow-ai` (moved out of OneDrive to
  avoid sync and lock problems). It uses Python **3.12** via **uv**, with dependencies
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

**How to run and verify** (from `C:\dev\attendflow-ai`)
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

**How to run and verify** (from `C:\dev\attendflow-ai`)
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

**How to run and verify** (from `C:\dev\attendflow-ai`)
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

**Next: Phase 3**
- The LLM layer: tools the agent can call over the engine results (read-only), plain-language
  explanations and worker messages grounded in `details` and `evidence`, Pydantic-validated
  output with retry and a template fallback.
- Still open: fix_options for P3, P4 and P7; an optional P17 demo case.
