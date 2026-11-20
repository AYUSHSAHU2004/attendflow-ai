# Demo walkthrough (Phases 10-14)

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

## 8. No reply: reminder, supervisor, payroll (Phase 13)

Run on a fresh reset with `ATTENDFLOW_DEMO_MODE=true` (no LLM key needed; the scheduler
timer can stay off). The numbers come from the Phase 13 live check (separate database
`attendflow_phase13`, API :8013, Vite :5185).

1. Demo reset as E201. The scheduler panel on `/admin` shows **Clock: Thu 16 Apr 08:00**,
   "data as of Thu 16 Apr 08:00", and the limits (reminder 8 h, supervisor 24 h, payroll
   +24 h).
2. Simulate punch: Neha Gupta (E004), Clock in, 15-04-2026, **08:58**, Send. Then **Run
   scheduler now**: "1 investigated, 1 message sent". Neha's inbox (`/?as=E004`) has the
   question. Do not answer.
3. Click **+8 h**. The panel says "Demo clock is now Thu 16 Apr 16:00. Run the scheduler
   (or wait for the next cycle) to apply." **Run scheduler now**: "1 reminder sent".
   Neha's inbox shows **Reminder: we still need your answer about Wed 15 Apr. If we don't
   hear from you by Fri 17 Apr 08:00, your supervisor will review it using the records.**
4. Click **+8 h** twice (Fri 17 Apr 08:00), **Run scheduler now**: "1 sent to the
   supervisor (no reply)". On `/supervisor` Ravi's queue shows Neha with **NO REPLY ·
   24 H**; the card says "Neha Gupta has not replied for 24 h." with **Decide on the
   evidence without Neha's reply** and **Send to payroll**. Leave it.
5. Click **+1 day**, **Run scheduler now**: "1 sent to payroll (no reply)". `/admin`
   shows **Stuck (no reply): 1**; click it. Neha's row: **Escalated · Needs your decision
   · Sent to payroll · no reply · 48 h**. The detail lists each step with its time
   (waiting since 16 Apr 08:00, reminder 16:00, supervisor 17 Apr 08:00, payroll
   18 Apr 08:00), and every audit summary says "Nothing was changed". Neha's inbox now
   says "With payroll. Payroll is handling this now. Please speak to your supervisor."
6. Priya: **Open the decision card**, tick **Decide on the evidence without Neha's
   reply**, type a reason (10+ characters), tick **I'm confirming this time without the
   worker's reply**, **Approve without reply**. The 18:00 clock-out is written by
   `fixes/apply.py`; detection then opens Neha's P3 and P4 (08:58 to 18:00 is just over
   9 h). Neha's inbox shows **Decided without your reply: Set clock-out to 18:00.** with
   the reason.
7. Late reply: reset and repeat steps 2 to 4, then answer **Yes** in Neha's inbox (the
   question is still there, marked "Your supervisor is now reviewing this. You can still
   answer."). The case stays with Ravi, marked **Replied late**; moving the clock further
   sends nothing to payroll. Answering **No** instead sends it back to Neha for the
   actual time (normal Phase 8), with a fresh 8 h reminder clock.
8. Amit's P1 is untouched throughout: open with Ravi, only the `detected` audit row.

**Demo note: one step per cycle.** The ladder takes at most one step per case per cycle,
so the worker always gets the reminder before anyone else is brought in. If you jump the
clock straight to +1 day (or more) after the question, press **Run scheduler now** twice
(or wait two cycles): the first run sends the reminder, the second brings in the
supervisor. The steps above move the clock in smaller jumps, so one run per jump is
enough there.

## 9. What did the agent do, and who approved it? (Phase 14)

Run right after section 8 steps 1 to 5 (Neha's silent path), then undo Sana's
auto-resolve as Ravi (`/supervisor` → **Auto-resolved for my team** → Sana's P2 →
**Undo**, reason "Sana says the second tap was a real re-entry"). Numbers are from the
Phase 14 live check (database `attendflow_phase14`, API :8001, Vite :5174).

1. Open `/activity` (or the **Activity and autonomy** link on `/admin`). Priya sees
   everything. The summary strip: **1** case investigated by the agent, **1** message,
   **1** reminder, **1** auto-resolved (1 undone), **1** escalated by silence, **0**
   approvals, **0** rejections, **1** device punch.
2. Read the feed from the bottom up: the rule engine finds the 17 cases and auto-resolves
   Sana's P2; **GATE-01 recorded a clock-in for Neha Gupta at Wed 15 Apr 08:58**; the
   rule engine opens her P1 and closes her P10; the scheduler starts an investigation; the
   LLM agent investigates with read-only tools; the scheduler asks Neha; the no-reply
   ladder sends a reminder (Thu 16:00), brings in Ravi (Fri 08:00) and payroll (Sat 08:00),
   each "Nothing was changed"; Priya's demo clock moves sit between them; Ravi undoes
   Sana's auto-resolve with his reason. Each row says who acted: System (Rule engine,
   Scheduler, No-reply ladder), LLM agent, Device, or a named person.
3. Filters: **Show → Human decisions only** leaves Ravi's undo and Priya's clock moves.
   **Autonomous only** plus `E004` in **Case or employee** leaves Neha's automatic story
   (the summary strip follows the filters). Dates filter on workflow time.
4. Click **Neha Gupta · P1** on any row: the same `/admin` case detail opens beside the
   feed, with the tool calls and a one-line result for each.
5. Ravi's view: `/activity?as=E101` (dev builds), or **Team activity** on `/supervisor`.
   Only Inbound cases; no device punches or demo-clock rows. Opening Neha's P1 shows his
   normal case card, **read only** ("this case is with Priya Sharma"), with **How it was
   checked** (each tool and its result) and no decision buttons. Sunita sees only
   Outbound rows.
6. **Autonomy** tab: every action, its actor (Code, System, LLM agent, Device, Human),
   the approval it needs, whether it can be undone, and its guardrail, then the "Never
   allowed" rows (the LLM never writes timecards or picks a fix, nobody calculates pay,
   silence is never a Yes, nothing outside the table). The README section "Autonomy and
   guardrails" is generated from the same registry, and tests fail if either drifts.
7. Amit's P1 is still untouched: open with Ravi, only the `detected` row.

## 10. Operations dashboard (Phase 15)

Use a fresh demo database, for example `attendflow_phase15`, separate from any open
session. Set `DATABASE_URL` to that database, migrate it with `uv run alembic upgrade head`,
and set `ATTENDFLOW_DEMO_MODE=true` and `SCHEDULER_ENABLED=false`. For a template-only
demo, set `LLM_BASE_URL=http://127.0.0.1:1/v1` and confirm port 1 has no listener. This
also prevents a key loaded from `.env` from sending a request to the configured provider.
If running the API and Vite on alternate ports, set `VITE_API_BASE_URL` to the API
origin and add the Vite origin to `ATTENDFLOW_CORS_ORIGINS`.

1. Seed the isolated database once if it is empty. As Priya on `/admin`, reset the demo
   and open **Operations dashboard**. Expect 16 active cases, **1 of 17** resolved
   without a human, and Meena at 36 h worked + 12 h scheduled = 48 h projected
   against the 40 h limit.
2. Go back to `/admin` and simulate Neha (E004) clocking in on 15 April at **08:58**.
   Run the scheduler once. Reopen the dashboard and verify the extra P1 and one case
   waiting for its first reminder. Neha's absence (P10) closes because the data changed.
3. Advance the demo clock by **+8 h**, then run the scheduler once. Reload the dashboard.
   Expect one reminded case and **Stuck: 1**. Waiting age moves to **8 to under 24 h**.
   Compare the matching cases on `/admin` and the reminder event on `/activity`.
4. On `/supervisor`, undo Sana's P2 as Ravi. Reload the dashboard to see P2 in open work,
   one more active case and **0 of 17** resolved without a human. `/activity` retains
   the one original auto-resolve and adds the undo.
5. Open **Operations dashboard** from `/supervisor` for Ravi's Inbound view. In a dev
   build, `/supervisor/dashboard?as=E102` opens Sunita's Outbound view. Confirm the
   workloads, case counts and overtime workers are scoped to the current team.
6. Click a severity or policy in Priya's view and verify the matching active cases.
   Apply a date range and check that the link carries it. At phone width (375 px),
   check that the panels stack without horizontal page scrolling. In Amit's P1
   detail, verify that the case is still open with only the `detected` audit row.

## Also worth showing

- Refusals: `/admin?as=E101` (dev builds only) shows "Only the payroll admin can open
  this page." The API returns 403 `admin_only` for anyone but E201.
- `POST /api/seed` resets everything for another run.

## 11. Payroll readiness and human sign-off (Phase 16)

1. Use a separate demo database and ports if the shared app is in use. Migrate it to
   head. Start the API with `ATTENDFLOW_DEMO_MODE=true`,
   `ATTENDFLOW_DEMO_EXTRA_WEEK=true`, `LLM_BASE_URL=http://127.0.0.1:1`,
   `LLM_API_KEY=` and `SCHEDULER_ENABLED=false`. Keep the default attendance cutoff.
2. Seed once on an empty demo DB with `POST /api/seed`, then reset with
   `POST /api/admin/demo/reset` as E201. Check that the reset still reports 17
   findings. Open **Payroll readiness** from **All exceptions** or the dashboard.
3. The week of 13 April is **Blocked** and **In progress**. Open a reason's case
   link and check the next owner. Amit's planted P1 is still open. There is no sign-off
   button. To show the explicit refusal, run this against the demo API port:

   ```sh
   curl -i -X POST http://localhost:8000/api/payroll/2026-04-13/sign-off \
     -H "X-Actor-Id: E201" -H "Content-Type: application/json" -d '{}'
   ```

   The API returns 409 `payroll_not_signable`. Moving the demo clock only advances
   workflow time. The attendance week still cannot be signed.
4. Select Monday **6 April 2026**, then **View week**. The complete earlier week
   shows **Ready**. Choose **Sign off week**, add an optional note, and confirm.
   Check that Priya and the workflow time appear on the sign-off.
5. Choose **Reopen week**, enter `Demonstrate a follow-up review`, and confirm.
   The page shows **Reopened** and allows a new sign-off. Open **Activity and autonomy**
   as Priya to see both decisions and the reopen reason. The reset and sign-off leave
   Amit's planted P1 untouched.
6. Open `/supervisor/payroll` for Ravi's read-only view. Check that it shows only
   Inbound, then narrow the viewport to phone width and verify the rows stack.
7. The backend test `test_closed_week_becomes_ready_with_notes_after_a_human_decision`
   uses an isolated fixture to remove a clock-out in the prior week. It covers
   **Blocked**, reminder, supervisor ownership, and **Ready with notes** after an
   explicit decision without the worker. The default demo has pending leave and
   other blockers. The optional seed week stays clean for recording sign-off.

## 12. Daily briefing and Amit's phone (Phase 17)

1. Use a separate demo DB and ports if the shared app is in use (the live check used
   `attendflow_phase17`, API :8017, Vite :5187; launch configs `phase17-api`,
   `phase17-api-live` and `phase17-web`). Migrate to head, `POST /api/seed` once, then
   `POST /api/admin/demo/reset` as E201 (17 findings).
2. **Offline first.** Start `phase17-api` (the LLM address points at nothing). Open
   `/admin`: **Today's briefing · All teams** shows the template, labelled **Template (LLM
   unavailable)**: 16 active cases, Sana's auto-resolved P2 (1 of 17, 5.9%), 15 cases
   blocking payroll for the week of 2026-04-13, Meena's 48 projected hours against the
   40 h limit, and one line per team. Click a case ID: the case opens in the detail panel.
3. Open `/supervisor` as Ravi: the card says **Inbound team** and shows only Inbound
   cases and names (11 active, 1 of 12 closed without a person).
4. **Amit on a phone.** As Ravi, investigate and ask Amit about `P1-E001-2026-04-14`
   (the card's **Investigate** and **Ask the worker** buttons, or the API). Open `/` at
   375 px wide (phone, light or dark). Amit sees **Hi Amit**, **Question 1 of 1** and big
   **Yes / No** buttons. Tap **No**, type "No, I stayed late. Left around 6:30 pm after
   loading the truck." and **Send**. Without an LLM the time cannot be read, so the
   confirmation says **One more step** and the exact-time field appears. Enter 18:30 and
   **Send time**: "18:30 sent to your supervisor. This makes the day 8.5 h ...".
   **See my history** shows the question, Amit's own words, the time and **With your
   supervisor**.
5. **One real briefing** (only with a key in `.env`). Restart the API as
   `phase17-api-live` and press **Refresh** on `/admin` once (or
   `curl -X POST localhost:8017/api/briefing/refresh -H "X-Actor-Id: E201"`). The label
   turns to **Written by the LLM from verified facts**; the footer shows the LLM calls and
   any failed checks. A second Refresh within 5 minutes is refused (429), and reading the
   page again makes no LLM call until the facts change.
6. Open **Activity and autonomy** as Priya: "Asked for a fresh daily briefing (all teams)",
   "Wrote the daily briefing (all teams) from verified facts; every check passed" or
   "Showed the template briefing (...): no LLM is configured". The Autonomy tab lists
   **Write the daily briefing** (LLM agent), **Use the template briefing** (system) and
   **Ask for a fresh briefing** (supervisor or payroll admin).
7. Amit's planted P1 is untouched by any briefing: its audit trail shows only `detected`
   until a person acts.
