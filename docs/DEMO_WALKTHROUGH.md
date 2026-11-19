# Prototype demo walkthrough (Phase 10)

The exact clicks for the prototype demo: Priya's list, Amit's missed clock-out from
detection to approval, and the reject path. About 6 minutes.

**Where the numbers come from.** Every count and hour below was read from a real run on
2026-11-19 (dev database reseeded, demo clock Thu 16 Apr 2026 08:00). The rule engine and
the database computed them; nothing on these pages is typed in by hand. If you change the
generator or `policy.json`, the numbers on screen change with it. The end-to-end tests
(`tests/test_e2e_prototype.py`) read these values from the engine instead of hard-coding
them.

**With or without an LLM key.** The run below had no `LLM_API_KEY`. Each LLM step then
falls back, and the audit log records why: the investigation uses the engine template, the
question to Amit uses the template, and Amit types his time into the manual field. With a
key, the model writes the investigation and the question, and it reads "around 7:30ish" as
an approximate 19:30 that Amit confirms with one click. All later steps are identical.

## 0. Start

```bash
docker compose up -d db
python -m uv run alembic upgrade head
python -m uv run attendflow-api          # terminal 1: http://localhost:8000
npm --prefix frontend run dev            # terminal 2: http://localhost:5173
curl -X POST localhost:8000/api/seed
curl -X POST localhost:8000/api/detection/run
```

Detection reports `found: 17`, `auto_resolved: 1` (Sana's duplicate tap, P2).

## 1. Priya's list (`/admin`)

Open `http://localhost:5173/admin` (acting as Priya, E201).

- Counters: **17 all, 16 open, 0 waiting for worker, 0 waiting for supervisor,
  0 escalated, 1 resolved, 0 rejected, 1 auto-resolved.** The database counts them.
- Above the counters (Phase 12): **"1 of 17 exceptions resolved without a human (5.9%)"**,
  with "P2: 1 auto-resolved" under it. Code counts it from the database.
- The table is sorted by severity, then date. Show the filters: Status, Policy, Team,
  Employee, and the name search (type `amit`).
- Click a counter (for example **Open**) to filter by that status. **Clear filters** resets.

## 2. Investigate Amit's case

Ravi investigates and asks Amit from the `/dev` page. **Ask worker** is enabled only after
an investigation on that page.

1. Open `http://localhost:5173/dev`. The ID field shows `P1-E001-2026-04-14`.
2. Click **Investigate**, wait for it to finish, then click **Ask worker**.
   The page says "Question sent."

(Priya can also investigate any open case from her detail panel with **Investigate**. This
is shown in step 6 on Meena's case.)

## 3. Amit answers (`/`)

1. Open `http://localhost:5173/`. Amit sees "Your clock-out is missing. Did you leave
   at 18:00?"
2. Click **No**, type `stayed late to unload the truck, left around 7:30ish`, click
   **Send**.
3. Without a key: enter **19:30** in **Exact clock-out time** and click **Send time**.
   (With a key: confirm the suggested 19:30.)
4. The receipt is built by code from the re-check: "This makes the day **9.5 h**, over the
   9 h daily limit. The week is projected at **41.5 h**, over the 40 h weekly limit."

## 4. Ravi approves (`/supervisor`)

1. Open `http://localhost:5173/supervisor` (Ravi, E101). Amit's case is in the queue.
2. The card shows Amit's own words, the confirmed time 19:30, and the re-check:
   - Day worked **9.5 h**, week projected **41.5 h** (limit 40 h)
   - New: **P5 risk** (week of 2026-04-13): 25.5 h worked + 16 h scheduled = 41.5 h > 40 h
   - New: **P3 breach** (2026-04-14): 9.5 h worked > 9 h daily limit
   - Resolves: P1 breach (2026-04-14)
3. Click **Approve**. The confirmation step lists the two new exceptions. Click
   **Approve anyway**.
4. The page says: "Approved for Amit Verma: Set clock-out to 19:30. New exceptions opened:
   P5-E001-2026-04-13, P3-E001-2026-04-14." Code wrote a correction punch (the old row
   is never deleted) and detection ran again.

## 5. Back to Priya: updated counters and the audit trail

1. Open `/admin` again. Counters: **19 all, 17 open, 2 resolved, 1 auto-resolved.** The
   two new cases are open, and Amit's P1 is resolved.
2. Search `amit` and open the P1 row. The panel shows the issue, the cited policy,
   evidence, the investigation (marked **engine template**), Amit's message and reply,
   the re-check, the fix options with the consequence note, and **Applied: Set
   clock-out to 19:30**.
3. Scroll to **Audit trail**. Oldest first:
   detected → investigation started → model call failed (no key) → investigation
   finished → investigation stored from the template → Ravi asked the worker → message
   written by the template → Amit answered No ("…7:30ish") → no usable time read
   (manual field) → Amit confirmed 19:30 (typed in) → Ravi approved → detection re-ran
   (new P5, P3).

## 6. The reject path (Meena's weekly overtime)

1. In `/admin`, open **Meena Iyer, P5, Mon 13 April 2026** ("36 h worked + 12 h
   scheduled = 48 h > 40 h (over by 8 h)"). Click **Investigate**. The panel says
   "Investigation stored", and the row reads "investigated → supervisor".
2. In `/supervisor` (Ravi), open Meena's case, click **Reject**, type
   `Overtime was never agreed for this week`, click **Send reject**.
   The page says it went to the payroll admin (E201).
3. Ravi can no longer open it: `GET /api/supervisor/cases/P5-E002-2026-04-13` with
   `X-Actor-Id: E101` returns 403 `not_assigned`.
4. In `/admin`, click the **Escalated: 1** counter. Meena's row shows **Needs your
   decision**. Open it, click **Open the decision card**, then **Reject**. The card says
   "Your reject is final." Type `Agree with Ravi: no overtime this week` and send.
5. Counters: **19 all, 16 open, 2 resolved, 1 rejected, 0 escalated.** Meena's audit
   trail ends with Ravi's reject (his reason) and Priya's final reject (her reason).
   No data changed.

## 7. Auto-resolve and undo (Phase 12)

Run this on a fresh reset (`ATTENDFLOW_DEMO_MODE=true`, no LLM key needed). The numbers
below come from the Phase 12 live check.

1. Demo reset (`POST /api/admin/demo/reset` as E201). `/admin` shows **1 of 17 (5.9%)**.
2. Open **Sana Khan, P2, Mon 13 April 2026**. The blue **Auto-resolved by the system**
   box shows why it was allowed ("2 'in' taps 2 min apart, within the 5 min duplicate
   window"), what changed ("P0005 clock-in 08:59: voided"), the policy text, and **Undo**.
3. Click **Undo**, type a reason (10+ characters), **Confirm undo**. The page says
   "Undone: 1 punch restored. The case is open for a person." P0005 is no longer voided.
   The metric becomes **0 of 17**, and the box shows who undid it and why.
4. Simulate punch: Neha Gupta (E004), Clock in, 15-04-2026, **09:02**, Send. The notice
   lists new P1 and P7 cases and the closed P10. The metric is **1 of 18 (5.6%)**, and a
   footnote says 1 case was closed because the data changed (Neha's P10, not counted).
5. Open `/supervisor` (Ravi). **Auto-resolved for my team** lists Sana's undone P2 and
   Neha's P7. Undo Neha's P7 with a reason: "Undone. Nothing to restore; the case is
   open for a person." Both cases are now in Ravi's queue marked "auto-resolve undone".
   `/admin` shows **0 of 18**, "P2: 0 auto-resolved, 1 undone · P7: 0 auto-resolved,
   1 undone".
6. Amit's P1 is untouched: still open with Ravi, only the `detected` audit row.

## Also worth showing

- Refusals: `/admin?as=E101` (dev builds only) shows "Only the payroll admin can open
  this page." The API returns 403 `admin_only` for anyone but E201.
- `POST /api/seed` resets everything for another run.
