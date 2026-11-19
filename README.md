# AttendFlow AI

An AI agent that cleans attendance data **before payroll**. It finds timecard exceptions
(missed punches, overtime risk, schedule conflicts, policy breaches, leave conflicts),
investigates them, proposes policy-compliant fixes, asks the worker what really happened,
and sends the case to a supervisor for approval. It does **not** calculate pay.

Built for the AI Innovation Challenge, Problem 5: Time & Attendance.

## Core design rule: "Code decides, the LLM talks"

| Deterministic code (no LLM) | LLM (open-weight, validated) |
|---|---|
| Finds every exception from `data/policy.json` limits | Investigates by calling read-only tools |
| Calculates hours, picks the policy ID | Explains cases in plain language |
| Builds the fix options | Writes messages to workers |
| Applies fixes after human approval | Extracts structured data from free text |
| Writes the audit log | Writes summaries |

The LLM can never write to timecards. Every LLM output is validated with Pydantic; on
failure it retries once, then falls back to a template or a manual form. The app works
with the LLM switched off.

## Users

- **Priya** (payroll admin): all exceptions, audit log, payroll readiness.
- **Ravi** (shift supervisor, Inbound team): approves, edits or rejects fixes for his team.
- **Amit** (warehouse worker): confirms what really happened.

## Repo layout

```
backend/attendflow/   Python package (config, data, policy, rule engine, DB, fixes, cases, API, LLM client)
frontend/             React + TypeScript app (from a later phase)
data/                 Demo CSVs, policy.json (limits), policy.md (plain-language policy)
docs/                 PROGRESS, PLANTED_CASES, LLM_LICENCE
tests/                pytest suite
```

## Quickstart

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/) (`pip install uv`).

```bash
uv sync
```

```bash
cp .env.example .env   # then put your Groq key in LLM_API_KEY
```

```bash
uv run attendflow-validate        # checks all CSVs + policy files
uv run attendflow-detect         # rule engine: every timecard exception (P1-P17)
                                  #   --fixes, --json, --employee E007, --policy P11,P12
uv run attendflow-llm-test        # sends one prompt to the configured model
uv run pytest                     # runs the tests
uv run attendflow-generate-data   # rebuilds data/*.csv (deterministic)
```

### Backend API (PostgreSQL + FastAPI)

Needs Docker. The database listens on **localhost:5433**.

```bash
docker compose up -d db           # PostgreSQL 16 (+ a test database)
uv run alembic upgrade head       # create the tables
uv run attendflow-api             # http://localhost:8000/docs
```

In `/docs`: `POST /api/seed` (demo reset), then `POST /api/detection/run` (17 exceptions).
Acting endpoints need an `X-Actor-Id` header: E101 Ravi, E102 Sunita (supervisors),
E201 Priya (payroll admin), E001 Amit (worker). Only the person the case is assigned to
can act. A fix is applied by code, in one transaction with its audit row, only after
approval. A supervisor's reject escalates the case to Priya.

### Agent tools (read-only)

Six tools the agent calls while investigating: `get_schedule`, `get_leave`,
`get_leave_balance`, `get_punches`, `get_policy` and `run_checks` (tests a proposed change
in memory and reports the violations it would cause). They read the database in a
read-only transaction and never write.

```bash
uv run attendflow-tools list
uv run attendflow-tools get_punches employee_id=E001 date=2026-04-14
uv run attendflow-tools get_policy policy_id=P3      # add --csv to read data/*.csv instead
```

If `uv` is not on your PATH, use `python -m uv` instead.

## Demo data

One demo week, Mon 13 to Sun 19 April 2026, with a public holiday on Tue 14 April.
The demo clock ("as-of") is **Thu 16 April 2026, 08:00**. See
[docs/PLANTED_CASES.md](docs/PLANTED_CASES.md) for every planted exception and the policy
it should trigger.

## LLM

Default: `openai/gpt-oss-120b` (open-weight, Apache 2.0) on Groq, through an OpenAI-compatible client, so Together
or a local Ollama model is a `.env` change. Licence notes: [docs/LLM_LICENCE.md](docs/LLM_LICENCE.md).

## Status

See [docs/PROGRESS.md](docs/PROGRESS.md).
