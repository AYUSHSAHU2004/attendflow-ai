# AttendFlow AI

An AI agent for timecard exceptions. It finds them, investigates, proposes a fix, asks the worker, and then asks a human to approve. Built for the AI Innovation Challenge, **Problem 5: Time & Attendance**.

> **Code decides. The LLM talks. Humans approve.**

[![CI](https://github.com/AYUSHSAHU2004/attendflow-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/AYUSHSAHU2004/attendflow-ai/actions)

Jump to: [Overview](#1-project-overview) · [Flow and diagrams](#2-project-flow-and-design-diagrams) · [Data schema](#3-data-schema) · [Role-wise functionality](#4-role-wise-functionality) · [LLM layer](#7-the-llm-layer) · [Safety](#8-harness-and-safety-design) · [Testing](#13-testing-and-ci) · [Deployment](#14-deployment)

## Quick links

| What | Link |
|---|---|
| Demo video (max 10 minutes) | TBD: https://drive.google.com/file/d/17fjs_meoj21YX5_79ZmOxbu1q62uL71D/view?usp=drive_link |
| Slides | TBD: https://docs.google.com/presentation/d/1Gr98qtUfpfETGP0iD6v2JVpKVr2OCoEv/edit?usp=drive_link&ouid=114416998967196537894&rtpof=true&sd=true |
| Source code | https://github.com/AYUSHSAHU2004/attendflow-ai |

## Team

| Member | Resume |
|---|---|
| Amarnath | TBD: https://drive.google.com/file/d/1UnyzzKv6jpk0sAWmTUNk93wO7YaUmbuC/view?usp=sharing |
| Anurag | TBD: https://drive.google.com/file/d/16vB0Z9RhSRgNCL-spDMYH3f_6d8mjVqj/view?usp=sharing |
| Ayush | TBD:  https://drive.google.com/file/d/1WraFvf-BwIz4MDNL-wn6UMYiV-IOoYv8/view?usp=drivesdk |
| Maharshi | TBD:https://drive.google.com/file/d/1OIe6bFt7qmkIK-JWEWphJn5Eekw2KsL9/view?usp=drivesdk |
| Saurav | TBD:  https://drive.google.com/file/d/1-iRw9F-VFXcj8D54RYSJXj_Ws2pjPcTk/view?usp=drivesdk|
| Arnav | TBD: https://drive.google.com/file/d/1Uli4YYR_CCluq0EEJk2BT3IuYC6Ess2y/view?usp=sharing |

## Run it locally

Prerequisites: Python 3.12 with `uv`, Node.js, Docker (for PostgreSQL), and optionally a Groq API key. Without a key, every LLM feature uses its template fallback and the app still works.

**1. Install and start the database**

```bash
git clone https://github.com/AYUSHSAHU2004/attendflow-ai.git
cd attendflow-ai
uv sync
docker compose up -d            # PostgreSQL on port 5433 (TBD: confirm the compose file name and service)
export DATABASE_URL='postgresql+psycopg://attendflow:attendflow@127.0.0.1:5433/attendflow'
.venv/bin/alembic upgrade head
```

**2. Set the login mode** (real email and password login)

```bash
export ATTENDFLOW_DEPLOYED=false ATTENDFLOW_AUTH_MODE=session
export ATTENDFLOW_COOKIE_SECURE=false ATTENDFLOW_TRUSTED_PROXY=false
export ATTENDFLOW_DEMO_MODE=true ATTENDFLOW_DEMO_RESET_ENABLED=true
export ATTENDFLOW_SESSION_SECRET="$(openssl rand -hex 32)"
export ATTENDFLOW_DEMO_PASSWORD="$(openssl rand -hex 24)"
echo "$ATTENDFLOW_DEMO_PASSWORD"     # this is the password for all demo accounts
```

For a quick start without login, skip this step. The default `header` mode is for local development and tests only.

**3. Seed the demo data and run the API**

```bash
.venv/bin/python -m attendflow.scripts.auth_cli seed-demo
.venv/bin/attendflow-api --port 8011
```

**4. Run the frontend** (a second terminal)

```bash
npm --prefix frontend ci
ATTENDFLOW_VITE_PROXY=http://127.0.0.1:8011 VITE_API_BASE_URL=/ \
  npm --prefix frontend run dev -- --port 5181
```

Open http://localhost:5181 and sign in with one of the demo accounts and the password from step 2.

| Role | Demo account |
|---|---|
| Worker | `amit@demo.attendflow.test` |
| Supervisor | `ravi@demo.attendflow.test` |
| Payroll admin | `priya@demo.attendflow.test` |

TBD: confirm the three emails against the seed output.

**5. Real LLM calls (optional).** Put the Groq key in your environment. Never commit it.

```bash
export GROQ_API_KEY=...        # TBD: confirm the exact variable name in .env.example
```

**Useful commands**

```bash
.venv/bin/python -m attendflow.scripts.auth_cli set-password E001 --email amit@demo.attendflow.test
.venv/bin/python -m attendflow.scripts.auth_cli unlock --email amit@demo.attendflow.test
bash scripts/check-all.sh              # the full check, same as CI
attendflow-autonomy --check            # the autonomy table check
```

TBD: the 100-employee dataset (`--profile large`) is described here once it exists.

---

## 1. Project overview

### The problem

A timecard exception is a punch day that does not look right: a missed clock-out, a duplicate punch, overtime over the limit, a leave and schedule conflict. Every one of them is a small investigation:

1. **Spot it.** Notice the exception among thousands of punches.
2. **Check it.** Read the policy, the schedule and the leave balance, and work out what really happened.
3. **Chase it.** Ask the worker, wait, remind, escalate, and find the right person to approve.

Payroll teams spend a large part of every pay period on this. The work is repetitive, but it is not safe to automate blindly, because a wrong fix changes someone's pay.

### What AttendFlow does

AttendFlow splits the work between code, an LLM and people, and keeps the boundaries strict.

| Step | Who does it | What happens |
|---|---|---|
| Detect | Code | A rule engine finds exceptions against 17 written rules (P1 to P17). No LLM is involved. |
| Investigate | LLM, with read-only tools | It reads punches, schedule and leave and writes a finding. |
| Propose | Code and LLM | A fix that follows policy, built from verified facts. |
| Ask | LLM text, from facts | The worker gets a short message. Silence triggers reminders. |
| Approve | A person | A supervisor or the payroll admin decides. Only `fixes/apply.py` can write to the timecard. |

- **Detection is deterministic code.** The same punches always give the same exceptions.
- **The LLM never writes to the system of record.** It investigates with read-only tools and writes text from facts that code has verified.
- **People approve.** Except for two narrow, undoable cases (P2 and P7), nothing changes without a human decision.
- **The system never computes payroll.** It tells people what needs attention. It does not decide what anyone is paid.

### Technology

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic, managed with `uv` |
| Database | PostgreSQL |
| Frontend | React, TypeScript, Vite, Vitest |
| LLM | `openai/gpt-oss-120b` (open-weight) on Groq, OpenAI-compatible client |
| CI | GitHub Actions: lint, format, tests, type-check, build, OpenAPI drift check, autonomy table check |
| Packaging | Dockerfile, Kubernetes (k3s) manifests |

---

## 2. Project flow and design diagrams

### 2.1 End-to-end flow

```mermaid
flowchart TD
  A["Punches, schedules and leave<br/>(device ingestion, seed)"] --> B["Rule engine checks P1 to P17"]
  B -->|no exception| Z["Nothing to do"]
  B -->|exception found| C["Case created"]
  C --> D{"Rule allows<br/>auto-resolve?<br/>(P2, P7 only)"}
  D -->|yes| E["Auto-resolve through the normal<br/>apply path, recorded and undoable"]
  D -->|no| F["Investigate<br/>LLM with read-only tools"]
  F --> G["Propose a fix<br/>from verified facts"]
  G --> H["Ask the worker<br/>short message"]
  H -->|worker replies| I["Reply is read and added<br/>to the case"]
  H -->|no reply| J["No-reply ladder:<br/>remind, then escalate"]
  J --> I
  I --> K["Supervisor or payroll admin<br/>reviews the evidence"]
  K -->|approve or edit| L["fixes/apply.py writes the change"]
  K -->|reject| M["Case closed, no change"]
  L --> N["Audit trail and activity feed"]
  E --> N
  M --> N
  N --> O["Payroll readiness and sign-off"]
```

### 2.2 Case lifecycle

TBD: confirm the state names against the code. The shape below is conceptual.

```mermaid
stateDiagram-v2
  [*] --> Detected
  Detected --> AutoResolved: P2 or P7, auto-resolve on
  Detected --> Investigating: person or scheduler starts it
  Investigating --> Proposed: finding validated
  Investigating --> Proposed: template fallback
  Proposed --> AwaitingWorker: message sent
  AwaitingWorker --> AwaitingApproval: worker replied
  AwaitingWorker --> AwaitingApproval: no-reply ladder ends
  AwaitingApproval --> Applied: approved
  AwaitingApproval --> Rejected: rejected
  AutoResolved --> Detected: undone with a reason
  Applied --> [*]
  Rejected --> [*]
  AutoResolved --> [*]
```

### 2.3 One case, step by step (missed clock-out)

```mermaid
sequenceDiagram
  autonumber
  participant D as Punch device
  participant API as FastAPI service
  participant E as Rule engine
  participant L as LLM (Groq)
  participant W as Worker (Amit)
  participant S as Supervisor (Ravi)
  participant A as fixes/apply.py
  D->>API: punch (device key, insert-only)
  API->>E: check the day against P1 to P17
  E-->>API: exception found, case created
  S->>API: Investigate
  API->>L: case plus read-only tools
  L-->>API: finding and proposed fix
  API->>API: validate against the facts packet
  API->>W: short message
  W->>API: "left around 6:30"
  API->>API: reply read and added to the case
  S->>API: approve
  API->>A: apply the fix
  A-->>API: timecard changed, audit written
  API-->>W: shown in My history
```

### 2.4 System architecture

```mermaid
flowchart LR
  subgraph Browser
    UI["React + TypeScript UI<br/>worker, supervisor, admin"]
  end

  subgraph API["FastAPI service, single process"]
    AUTH["Auth and role guard"]
    ENG["Rule engine<br/>P1 to P17"]
    SCH["Scheduler thread"]
    INV["Investigator<br/>LLM, read-only tools"]
    MSG["Messages, briefing, Q&A<br/>LLM text from facts packets"]
    VAL["Grounding validator"]
    APPLY["fixes/apply.py<br/>the only timecard writer"]
    AUD["Audit trail and<br/>autonomy registry"]
  end

  DB[("PostgreSQL")]
  LLM[["Groq: gpt-oss-120b<br/>open-weight"]]
  DEV["Punch devices"] -->|"device key, insert-only"| API

  UI --> AUTH --> ENG
  SCH --> ENG
  ENG --> DB
  INV --> LLM
  MSG --> LLM
  LLM --> VAL --> MSG
  INV -->|read-only| DB
  UI -->|approve| APPLY --> DB
  ENG --> AUD
  APPLY --> AUD
  AUD --> DB
```

- **One API process.** A background scheduler runs inside it and uses a non-blocking lock, so a deployment must run exactly one replica.
- **One writer.** Only `fixes/apply.py` changes timecards. The seed and `ingest/punches.py` are insert-only. A static test and an SQL write-hook test enforce this on every CI run.
- **Same origin.** The Docker image builds the frontend and FastAPI serves it, so there is no CORS setup.

### 2.5 How every LLM text is produced and checked

```mermaid
flowchart LR
  Q["Request:<br/>message, briefing or answer"] --> F["Code builds a facts packet<br/>IDs, numbers, names, states"]
  F --> M["LLM writes the text<br/>no tools in this call"]
  M --> V{"Grounding validator:<br/>IDs, numbers, names,<br/>tense, status, bypass"}
  V -->|passes| OK["Shown to the user"]
  V -->|fails, first time| R["One correction retry"]
  R --> V
  V -->|fails again,<br/>or model slow, or 429| T["Template text shown,<br/>labelled Template"]
```

### 2.6 Sign-in flow

```mermaid
sequenceDiagram
  autonumber
  participant U as Browser
  participant API as FastAPI
  participant DB as PostgreSQL
  U->>API: POST /api/auth/login (email, password)
  API->>DB: look up employee, check lockout
  API->>API: verify password hash (same time for unknown emails)
  API->>DB: create session, 8 hour expiry
  API-->>U: HttpOnly signed session cookie
  U->>API: any request with the cookie
  API->>DB: load the session, role and team
  API->>API: role guard, then team or worker scope
  API-->>U: allowed data, or 401 or 403
  U->>API: POST /api/auth/logout
  API->>DB: revoke the session
```

---

## 3. Data schema

TBD: this is the conceptual schema, drawn from how the system works. Check the table and column names against the Alembic migrations before submission.

```mermaid
erDiagram
  TEAM ||--o{ EMPLOYEE : has
  EMPLOYEE ||--o{ SCHEDULE : works
  EMPLOYEE ||--o{ PUNCH : makes
  EMPLOYEE ||--o{ LEAVE : takes
  EMPLOYEE ||--o{ CASE : "has exceptions"
  EMPLOYEE ||--o{ SESSION : "signs in with"
  EMPLOYEE ||--o{ WORKER_QUESTION : asks
  CASE ||--o{ CASE_MESSAGE : contains
  CASE ||--o{ AUDIT_EVENT : "is recorded in"
  CASE }o--|| POLICY_RULE : "breaks"
  EMPLOYEE ||--o{ AUDIT_EVENT : "acts in"
  BRIEFING }o--|| EMPLOYEE : "for payroll admin"

  EMPLOYEE {
    string id PK
    string name
    string email
    string password_hash
    string role "worker, supervisor, payroll_admin"
    string team_id FK
    string supervisor_id FK
  }
  PUNCH {
    int id PK
    string employee_id FK
    datetime at
    string kind "in or out"
  }
  CASE {
    string id PK "P1-E001-2026-04-14"
    string employee_id FK
    string rule "P1 to P17"
    date work_date
    string state
    boolean fallback_used
  }
  AUDIT_EVENT {
    int id PK
    string case_id FK
    string actor
    string action
    datetime at
  }
  SESSION {
    string id PK
    string employee_id FK
    datetime expires_at
    datetime revoked_at
  }
```

Other tables the system uses: `settings` (the runtime overrides row), `briefings`, and `worker_questions`.

### Who can read or write what

| Data | Worker | Supervisor | Payroll admin | System (scheduler) |
|---|---|---|---|---|
| Own punches, schedule, leave | Read | Read | Read | Read |
| Other people's punches and cases | No | Own team only | All | All |
| Cases | Own, read | Own team, approve, edit, reject | All, approve, edit, reject, undo | Create, investigate within caps |
| Messages and replies | Reply to own | Read own team | Read all | Send reminders |
| Timecards | Never writes | Only through `fixes/apply.py` | Only through `fixes/apply.py` | Only through `fixes/apply.py`, P2 and P7 |
| Sessions and passwords | Own login | Own login | Own login, CLI for resets | None |
| Settings | No | No | Whitelist with bounds, blocked in Locked profile | Reads once per cycle |
| Audit and activity | Own history | Own team | All | Writes |

---

## 4. Role-wise functionality

### Worker (Amit, on a phone)

- Sign in with email and password. Lands on the inbox.
- Answers the short questions the system asks about flagged days, in plain words.
- Sees **My history**: own past cases and the fixes that were applied.
- **Ask** tab: asks about leave balance, schedule, own cases, own punches, a policy rule, or who the supervisor is. Answers are grounded in facts and labelled "Template" when the model is not used.
- Cannot see other people, cannot ask about pay, cannot request changes through Q&A. Those questions are refused by code with no LLM call.

### Supervisor (Ravi, Inbound team)

- Lands on the decision queue.
- Sees each case with the evidence (punches, schedule, leave), the finding and the proposed fix.
- Approves, edits or rejects. Approval goes through `fixes/apply.py`.
- Sees only the cases of their own team. Another team's case returns 403.

### Payroll admin (Priya)

- Dashboard of open cases, ageing and status.
- **Daily briefing**: a short summary checked against the facts, with caps on refreshes and daily LLM calls.
- **Payroll readiness** and sign-off: what still blocks payroll.
- Same decision rights as a supervisor, across all teams, plus undoing an automatic fix with a reason.
- **Activity and autonomy feed**: what the system did on its own, and what people did.
- **Settings**: change a whitelist of limits (auto-resolve switch, no-reply ladder hours, scheduler caps, briefing limits, overtime margin, Q&A limits) within bounds, with a history. Locked keys cannot be changed, and the Locked demo profile blocks changes.

### System (scheduler) and devices

- The scheduler runs detection on a cycle, and starts investigations within its caps. It reads the settings once per cycle.
- It may auto-resolve only P2 and P7, through the normal apply path, and every such action is undoable.
- Punch devices insert punches with a device key. They cannot read anything.

### Access matrix

| Area | Worker | Supervisor | Payroll admin | Anonymous |
|---|---|---|---|---|
| Login page and `/healthz` | Yes | Yes | Yes | Yes |
| Worker inbox, history, Ask | Own only | No | No | 401 |
| Decision queue and case view | No | Own team | All | 401 |
| Dashboard, briefing, payroll readiness | No | No | Yes | 401 |
| Activity and autonomy feed | No | No | Yes | 401 |
| Settings | No | No | Yes (not in Locked profile) | 401 |
| Punch ingestion | No | No | No | Device key only |

TBD: confirm each row against the access matrix test.

---


## 5. Screenshots

TBD: add the images under `docs/screenshots/` (see `docs/screenshots/README.md`).

| Screen | File |
|---|---|
| Login | `docs/screenshots/login.png` |
| Worker inbox (phone size) | `docs/screenshots/worker-inbox.png` |
| Supervisor case view | `docs/screenshots/supervisor-case.png` |
| Payroll admin dashboard | `docs/screenshots/admin-dashboard.png` |
| Daily briefing | `docs/screenshots/briefing.png` |
| Autonomy table | `docs/screenshots/autonomy.png` |


## 6. Policy rules (P1 to P17)

The engine checks every punch day against **17 written policy rules, P1 to P17**. The LLM never invents a rule: it can only explain a rule the engine has already applied.

Facts that hold for all rules:

- Only **P2 and P7** can be resolved automatically, and every automatic resolution can be undone with a reason.
- All other rules need a human to approve the fix.
- A day that has only a P17 case gets a fixed wording in the employee Q&A.

TBD: fill the table below from the code (rule ID, plain-English name, what it detects, and which test or demo case covers it).

| Rule | Name | What it detects | Auto-resolve | Covered by |
|---|---|---|---|---|
| P1 | TBD | TBD | No | TBD |
| P2 | TBD | TBD | Yes (undoable) | TBD |
| P3 | TBD | TBD | No | TBD |
| P4 | TBD | TBD | No | TBD |
| P5 | TBD | TBD | No | TBD |
| P6 | TBD | TBD | No | TBD |
| P7 | TBD | TBD | Yes (undoable) | TBD |
| P8 | TBD | TBD | No | TBD |
| P9 | TBD | TBD | No | TBD |
| P10 | TBD | TBD | No | TBD |
| P11 | TBD | TBD | No | TBD |
| P12 | TBD | TBD | No | TBD |
| P13 | TBD | TBD | No | TBD |
| P14 | TBD | TBD | No | TBD |
| P15 | TBD | TBD | No | TBD |
| P16 | TBD | TBD | No | TBD |
| P17 | TBD | TBD | No | TBD |

Case IDs follow the pattern `P<rule>-<employee>-<date>`, for example `P1-E001-2026-04-14`.


## 7. The LLM layer

The model is **gpt-oss-120b**, an open-weight model, served by Groq. It does three jobs and nothing else.

| Job | What it receives | What it produces |
|---|---|---|
| Investigate a case | The case, with read-only tools for punches, schedule, leave and policy | A structured finding and a proposed fix |
| Write for people | A facts packet built by code | A short worker message, a daily briefing, or an answer to an employee question |
| Classify a question | The employee's question, after the keyword matcher | One of the fixed intents (leave balance, my schedule, my cases, my punches, policy rule, my supervisor, unsupported) |

How it is kept honest:

- **Read-only tools.** The tool schemas expose reads only. They avoid constructs that Groq does not accept (`$ref`, `$defs`, `date-time`).
- **Facts packets without free text.** The packet holds IDs, numbers, names and states. It holds no free text that could carry an injected instruction.
- **Final answers without tools.** The model answers in a separate call with no tools, and the server parses and validates the result.
- **Grounding validator.** It checks case and employee IDs, numbers, names, tense, status wording, bypass attempts and false "nothing to report" claims. The briefing and the Q&A share this module.
- **One correction retry.** Only when validation fails, and with a hard maximum on calls per refresh (briefing: 2) and per question (Q&A: 3).
- **Template fallback everywhere.** If the model is slow, rate-limited (a Groq 429 counts as a provider error), or fails validation, the user sees a plain template. The UI labels it "Template". This is designed degradation, not an error.
- **Caps.** Per-hour and per-day limits for briefing and Q&A, plus an interval between briefing refreshes. They are environment settings and, for admins, runtime settings.
- **Diagnostics off in deployment.** `LLM_DIAGNOSTICS` must be off on a hosted instance.
- **Code pre-refusals.** Questions about other people, pay, change requests, or other languages are refused by code with **zero** LLM calls.


## 8. Harness and safety design

This is the part of the system we care about most.

**Single writer.** `fixes/apply.py` is the only module that changes timecards, schedule or leave. Tests enforce it statically and at the SQL layer.

**Autonomy registry.** `activity/autonomy.py` lists every action the system may take on its own, who may take it, and what it never does. The table in this README is generated from that registry and checked in CI, so the documentation cannot drift from the code. Every new audit action must be registered together with a test that asserts the refusal case.

<!-- AUTONOMY TABLE: keep the block that `attendflow-autonomy --write-readme` generates. Paste it here, between its own markers. -->

<!-- autonomy-table:start (generated by attendflow-autonomy; do not edit) -->
Generated from `backend/attendflow/activity/autonomy.py` by `python -m uv run attendflow-autonomy --write-readme`. A test fails if this copy is out of date, if any code path writes an audit action missing from the registry, or if a row's named tests do not exist.

| Action | Actor | Done by | Approval needed | Reversible | Guardrail |
|---|---|---|---|---|---|
| Find exceptions | Code | Rule engine | None | Not applicable | Deterministic rules with limits from policy.json, no LLM; never edits a timecard; never reopens a resolved or rejected case. |
| Re-run detection after a change | Code | Rule engine | None | Not applicable | Runs after an approved fix, an undo or a device punch; a failure never undoes the change and the next run picks it up. |
| Auto-resolve a low-risk exception | Code | Rule engine | None | Yes, with undo | Only P2 (duplicate tap) and P7 (late within grace), only if policy.json allows it and AUTO_RESOLVE_ENABLED is on; anything unclear is held for a person; the change is written by fixes/apply.py. |
| Run the scheduler cycle | System | Scheduler | None | Not applicable | Only the steps below, capped per cycle; old (backlog) and undone cases are left to people; one cycle at a time. |
| Start an investigation automatically | System | Scheduler | None | Not applicable | Only new open cases (or changed facts), at most SCHEDULER_INVESTIGATIONS_PER_CYCLE; the investigation itself is read-only. |
| Ask the worker automatically | System | Scheduler | None | Not applicable | Only when the stored investigation routes to the worker, at most SCHEDULER_MESSAGES_PER_CYCLE; a question changes no data. |
| Send one reminder (no reply) | System | No-reply ladder | None | Not applicable | Once per wait, after NO_REPLY_REMINDER_HOURS; fixed template, no LLM; changes no data. |
| Bring in the supervisor (no reply) | System | No-reply ladder | None | Not applicable | After NO_REPLY_SUPERVISOR_HOURS of silence; only changes who decides, never the data or the decision. |
| Bring in payroll (no reply) | System | No-reply ladder | None | Not applicable | NO_REPLY_ADMIN_HOURS after the supervisor was brought in and did not act; only changes who decides, never the data or the decision. |
| Stop the no-reply ladder | System | No-reply ladder | None | Not applicable | Any reply from the worker stops it, even a late one. |
| Investigate an exception | LLM agent | LLM agent | None | Not applicable | Read-only tools in a READ ONLY transaction; the draft is checked by Pydantic and code (exact quotes, numbers, stored options); retry once, then the engine template. |
| Write the message to the worker | LLM agent | LLM agent (template if it fails) | None | Not applicable | Validated by Pydantic, template fallback; it only asks, it never decides or changes data. |
| Read a time from the worker's reply | LLM agent | LLM agent | None | Not applicable | Only a candidate time, validated and re-checked by code; the worker must confirm it; never writes a timecard. |
| Record a punch from a device | Device | Punch device | None | No | Needs DEVICE_API_KEY; validated, never in the future, no exact duplicates; adds one row, never edits or deletes one (a correction voids it). |
| Answer the question (Yes/No, or a time) | Human | Worker | None | Not applicable | Only the worker who was asked; a typed time is validated and re-checked; the answer itself changes no data. |
| Ask the worker to confirm | Human | Supervisor or payroll admin | Supervisor (payroll admin once escalated) | Not applicable | Only the person the case is assigned to; changes no data. |
| Approve or edit a fix | Human | Supervisor or payroll admin | Supervisor (payroll admin once escalated) | No | Only the assignee; only a stored fix option with validated params; the worker's Yes where required; written only by fixes/apply.py in one transaction (old punches are voided, never deleted). |
| Decide without the worker's reply | Human | Supervisor or payroll admin | Supervisor (payroll admin once escalated) | No | Only after the ladder brought the supervisor in; a reason of 10+ characters; a punch time needs an explicit tick; still applied by fixes/apply.py. |
| Reject a fix | Human | Supervisor or payroll admin | Supervisor (payroll admin once escalated) | Not applicable | Only the assignee, with a reason; a supervisor's reject goes to payroll, only payroll's reject is final; changes no data. |
| Escalate to payroll | Human | Supervisor | Supervisor | Not applicable | Only the assignee, with a reason of 10+ characters; decides nothing and changes no data. |
| Undo an auto-resolve | Human | Supervisor or payroll admin | Supervisor (payroll admin once escalated) | No | The team's supervisor or payroll, with a reason; restores the exact before-values through fixes/apply.py; refused with no change if the data changed since; the case is never auto-handled again. |
| Move the demo clock forward | Human | Payroll admin | Payroll admin | No | Demo mode only (404 otherwise); forward only, at most +14 days; never changes what detection sees. |
| Sign off attendance readiness | Human | Payroll admin | Payroll admin | Yes, with undo | Only a closed period with attendance data and no blockers can be signed off. Changes to the reviewed data require a new human sign-off. |
| Reopen attendance readiness | Human | Payroll admin | Payroll admin | Yes, with undo | Requires a reason. Reopening preserves the audit history and source data. |
| Change a runtime setting | Human | Payroll admin | Payroll admin | Yes, with undo | Twelve whitelisted keys within fixed bounds, a reason of 10+ characters, an explicit confirm to turn auto-resolve on; refused in the deployed Locked profile. Never retroactive. Writes only the settings row and the audit log; reset is the undo. |
| Write the daily briefing | LLM agent | LLM agent | None | Not applicable | Only from a code-built facts packet scoped to the reader; every number, case ID, name and claim is checked by code, one correction, else the template. Changes no data. |
| Use the template briefing | System | Briefing service | None | Not applicable | Used when the LLM is off, fails, times out or its draft fails the checks; built by code from the same facts; stores a reason code only. Changes no data. |
| Ask for a fresh briefing | Human | Supervisor or payroll admin | Supervisor (payroll admin once escalated) | Not applicable | Own scope only (a supervisor sees their team); at most two LLM calls, a minimum interval and a daily call budget. Workers get 403. |
| Answer a worker's question | LLM agent | LLM agent | None | Not applicable | Own data only: the server sets the worker, code picks a closed intent and builds the facts; every number, date, ID and name is checked, one correction, else the template. Changes no data. |
| Use the template answer | System | Employee Q&A | None | Not applicable | Used when the LLM is off, fails, is rate limited, times out, is over its daily budget or fails the checks; built by code from the same facts; stores a reason code only. Changes no data. |
| Refuse a worker's question | System | Employee Q&A | None | Not applicable | Code refuses questions about other people, pay, changes, rule changes or other topics before any LLM call, with a fixed reply that names the supervisor. Changes no data. |

**Never allowed**

| Never | Who | Guardrail |
|---|---|---|
| Sign off an attendance period automatically | System | Payroll sign-off requires an explicit action by the payroll admin. |
| Write timecards, schedules or leave | LLM agent | Its tools are read-only (READ ONLY transaction, no writer imports); fixes/apply.py is the only writer and runs only after a person approves. |
| Approve or pick a fix on its own | LLM agent | Its proposal is a draft that must match a stored option; only a person's approve applies anything. |
| Calculate payroll or salaries | Anyone | There is no pay data in the database and no pay tool; the app only cleans attendance before payroll. |
| Treat silence as a Yes | No-reply ladder | The ladder only changes who is asked; deciding without the worker is a separate human action with a reason. |
| Auto-resolve anything but P2 and P7 | Rule engine | The code allows only P2 and P7, whatever policy.json says; the kill switch turns even those off. |
| Change policy rules, LLM settings or secrets while the app runs | Anyone | The settings API accepts only its whitelist. Policy.json rules and limits, the LLM key, URL and model, demo mode and clock, passwords, the database URL, the as-of time and every other server setting are refused (403 setting_locked). |
| Change, approve or promise anything from a worker's question | Employee Q&A | The Q&A reads in a READ ONLY transaction and imports no writer; code refuses change requests, and the checks reject promises, approval claims and other people's data. |
| Take an action that is not in this table | Anyone | A test scans the code, and another checks every audit row the test suite writes; both fail on an action missing here. |
<!-- autonomy-table:end -->

**Two automatic fixes only.** P2 and P7 can resolve on their own. Each is undoable, with a reason, and each shows up in the activity feed.

**Human approval.** Every other fix is approved by the supervisor or the payroll admin.

**No-reply ladder.** When a worker does not answer, the system reminds and then escalates on a schedule. The limits are saved on the case when the wait starts, so later settings changes never rewrite a running case.

**Scoped everywhere.** Workers see only their own data, including in Q&A. Supervisors see only their team's cases. The server decides this from the database, not from anything the browser sends.

**What the system never does:** compute payroll, change another person's data on a worker's request, or answer from facts it has not verified.


## 9. Feature details

**Detect and investigate.** The engine detects exceptions. The scheduler picks them up. A person or the scheduler (within caps) starts an investigation, which produces a finding and a proposed fix.

**Worker messages and replies.** The worker gets a short message and answers in plain words. The system extracts the meaning (for example, "left around 6:30") and puts it in the case.

**Decision queue.** Supervisors and the payroll admin see the case, the evidence and the proposed fix, and approve, edit or reject.

**Daily briefing.** A short summary for the payroll admin, built from a facts packet and checked by the grounding validator. It has caps on interval and on daily LLM calls.

**Employee Q&A.** Workers ask about their own leave balance, schedule, cases, punches, a policy rule, or who their supervisor is. Answers are scoped to the signed-in worker and grounded in facts. Audit actions: `qa_answered`, `qa_fallback`, `qa_refused`.

**Runtime settings.** The payroll admin can change a whitelist of settings with bounds and a history, without redeploying: auto-resolve switch, no-reply ladder hours, scheduler caps, briefing limits, overtime margin, Q&A limits. Locked keys cannot be changed. The Locked demo profile blocks changes entirely.

**Payroll readiness.** A page that shows what still blocks payroll and supports sign-off.

**Activity and autonomy feed.** A readable trail of what happened and who or what did it.

**Worker history.** Each worker can see their own past cases and fixes.

**Demo profiles.** `Locked` (runtime settings cannot be changed, for a public URL) and `Guided` (shows demo-account shortcuts on the login page), set by environment.


## 10. Authentication and roles

Employees sign in with their own **email and password**. PostgreSQL decides the role: `worker`, `supervisor` or `payroll_admin`.

- **Passwords** are stored as hashes and never logged.
- **Sessions** are stored in PostgreSQL. The cookie holds a signed, opaque session ID. It is HttpOnly and SameSite=Lax, and Secure when `ATTENDFLOW_COOKIE_SECURE` is true. Sessions last 8 hours and are revoked on logout and on password reset.
- **Lockout.** Five failed attempts within ten minutes lock that email or IP for ten minutes. Unknown emails and wrong passwords return the same error and take the same time.
- **CSRF.** Browser mutations require a same-origin `Origin`.
- **Behind a proxy.** The client IP comes from `X-Forwarded-For` only when `ATTENDFLOW_TRUSTED_PROXY` is true.
- **Auth modes.** `session` for deployments. `header` (the `X-Actor-Id` header) is for local development and tests only, and it is ignored completely in session mode.
- **Open endpoints.** `/healthz`, the login page and its assets, and `POST /api/auth/login`. Machine punch ingestion keeps its own device-key authentication. Everything else needs a session.
- **CLI.** `attendflow.scripts.auth_cli` sets passwords, seeds the demo accounts and clears lockouts.

Demo accounts use synthetic emails such as `amit@demo.attendflow.test`. All demo accounts share one password that comes from `ATTENDFLOW_DEMO_PASSWORD`. It is never stored in the repository.


## 11. Configuration

All settings are environment variables. `.env.example` is the source of truth. The main ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `ATTENDFLOW_AUTH_MODE` | `header` (dev, tests) or `session` (deployed) |
| `ATTENDFLOW_SESSION_SECRET` | Signs session cookies. At least 32 bytes. Required when deployed |
| `ATTENDFLOW_DEMO_PASSWORD` | Password for the synthetic demo accounts. Environment only |
| `ATTENDFLOW_COOKIE_SECURE` | Set the cookie Secure flag. True behind HTTPS |
| `ATTENDFLOW_TRUSTED_PROXY` | Trust `X-Forwarded-For` for the client IP |
| `ATTENDFLOW_DEPLOYED` | Switches on deployed-mode checks |
| `ATTENDFLOW_DEMO_MODE`, `ATTENDFLOW_DEMO_RESET_ENABLED` | Demo profile and the reset endpoint |
| `LLM_DIAGNOSTICS` | Extra model logging. Must be off in deployment |
| `BRIEFING_MIN_INTERVAL_SECONDS`, `BRIEFING_MAX_LLM_CALLS_PER_DAY` | Briefing caps |
| `QA_*` | Q&A caps, such as `QA_MAX_LLM_CALLS_PER_DAY` |

Admins can also change a whitelist of these limits at runtime from the settings panel, within bounds.


## 12. API overview

The OpenAPI schema is the source of truth. CI regenerates the TypeScript types from it and fails if they drift. Endpoint families:

| Family | Who | Notes |
|---|---|---|
| `/healthz` | Anyone | Health check, used by probes |
| `/api/auth/login`, `/logout`, `/me` | Anyone, then signed in | Session cookie |
| Worker inbox, history, Q&A | Worker | Scoped to the signed-in worker |
| Decision queue and cases | Supervisor, payroll admin | Supervisor sees own team only |
| Dashboard, payroll readiness, briefing, activity, settings | Payroll admin | Settings are locked in the Locked profile |
| Punch ingestion | Devices | Device key, insert-only |
| Demo reset | Demo mode only | Disabled unless enabled by environment |

TBD: list the exact paths from the OpenAPI document.


## 13. Testing and CI

Run everything the way CI does:

```bash
bash scripts/check-all.sh
```

Stop the API first. The tests use a real PostgreSQL database and run one at a time.

| Suite | Count |
|---|---|
| Backend (pytest, real PostgreSQL) | 1,080 passed, 2 skipped (opt-in live-model tests) |
| Frontend (Vitest) | 129 passed |

TBD: refresh these counts from `docs/PROGRESS.md` before submission.

What the tests cover:

- **Single writer.** A static test (no other module writes timecards) and an SQL write-hook test.
- **Autonomy registry.** Every audit action is registered and has a refusal-asserting test.
- **Grounding.** The briefing and Q&A validators have tests for wrong IDs, numbers, names, tense, status wording and false "empty" claims.
- **Golden sets.** `tests/qa_golden.json` for employee Q&A.
- **Access matrix.** For each endpoint family and each role, the expected allow or deny.
- **Login.** Success, failure, lockout, cookie flags, tampered and expired cookies, header ignored in session mode.
- **Frontend.** Components, route guards and logout behaviour.

CI runs on every push: lint and format, backend tests, frontend tests, type-check, production build, the OpenAPI drift check, and `attendflow-autonomy --check`. Tests never need an LLM key.


## 14. Deployment

**Docker.** The Dockerfile builds the frontend and serves it from FastAPI on the same origin, with a single uvicorn worker. Migrations run on start.

**Kubernetes (k3s on one VM).** TBD: verify against `docs/DEPLOY.md` once the cluster is up.

- Manifests live in `deploy/k8s/` (kustomize).
- The app is a Deployment with `replicas: 1` and the `Recreate` strategy, so two schedulers never run at once.
- PostgreSQL runs as a StatefulSet with a persistent volume.
- A ConfigMap holds the profile and limits. A Secret holds the session secret, the demo password, the database password and the Groq key. Only placeholders are in the repository.
- Traefik (shipped with k3s) is the ingress, with Let's Encrypt for HTTPS.
- Probes use `/healthz`.
- After the first deploy: `kubectl exec deploy/attendflow -- python -m attendflow.scripts.auth_cli seed-demo`.
- `scripts/smoke-deployed.py` signs in and checks the main pages with **zero model calls**.

**Render** (`render.yaml`) is kept as an optional alternative and has not been used for the demo.

**Rules for any hosted instance:** the Groq key lives only in the host or cluster secret, `LLM_DIAGNOSTICS` is off, and the session secret is set.


## 15. Evaluation

TBD: results of the mini evaluation (`docs/EVALUATION.md`) go here: how many seeded exceptions the engine detects, how many the investigator explains correctly, how often the grounding validator catches a bad draft, and how often the template fallback is used.


## 16. Mapping to the judging criteria

| Criterion | Weight | Where to look |
|---|---|---|
| Product value | 25% | Sections 1, 4 and 9: three role-based views, decision queue, briefing, payroll readiness |
| Harness engineering | 25% | Section 8: single writer, autonomy registry with a generated and checked table, grounding validator, caps, fallbacks |
| LLM implementation | 20% | Section 7: open-weight model, read-only tools, facts packets, validation, bounded retries |
| Engineering quality | 15% | Section 13: more than a thousand tests against a real database, CI with an OpenAPI drift check, Docker and Kubernetes |
| Demo | 15% | Live URL and video at the top of this file, plus `docs/DEMO_WALKTHROUGH.md` |


## 17. Limitations and future work

Stated honestly:

- **Login is email and password only.** There is no password reset by email, no signup and no single sign-on.
- **One API replica.** The scheduler thread requires a single process. Scaling out would need a leader lock.
- **Free-tier model limits.** Groq's free tier limits requests and tokens, so every LLM feature has caps and a template fallback.
- **Synthetic data.** The demo uses invented people and punches.
- **English only.** Other languages are refused in the Q&A.
- **More automatic fixes** are possible next steps, but each one would have to pass the same autonomy registry and refusal tests.


## 18. Repository layout

```
backend/attendflow/        API, rule engine, LLM layer, scheduler
  briefing/                Daily briefing: facts, generation, validation
  qa/                      Employee Q&A
  cases/                   Cases, worker history
  fixes/apply.py           The only timecard writer
  ingest/punches.py        Insert-only punch ingestion
  activity/autonomy.py     Autonomy registry
  grounding.py             Shared grounding validator
  runtime_settings.py      Runtime settings with bounds
  db/migrations/           Alembic migrations
backend/tests/             Backend tests, golden sets
frontend/src/              React UI (worker, supervisor, admin)
deploy/k8s/                Kubernetes manifests (TBD until K1)
docs/                      PROGRESS.md, DEMO_WALKTHROUGH.md, DEPLOY.md, screenshots
scripts/                   check-all.sh, smoke-deployed.py, start-deployed.sh
Dockerfile, render.yaml    Packaging
CLAUDE.md                  Working rules for the build process
```

TBD: confirm folder names against the actual tree before submission.
