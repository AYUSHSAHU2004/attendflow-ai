# AttendFlow Time & Attendance Policy

Version 2026.1, effective 1 January 2026. Applies to all hourly warehouse staff.

All times are local wall-clock times at the site. The work week runs Monday to Sunday.
The numeric limits below are mirrored in `policy.json`, which is what the system enforces.
Each section has the same parts: **Rule**, **Why**, **How it is checked** and **Allowed fixes**.
Fixes are applied only by the system after a supervisor approves them, unless the section
says the case is auto-resolved. Every auto-resolution is written to the audit log.

## P1: Every shift needs a clock-in and a clock-out

**Rule:** Every worked shift must have exactly one clock-in and one clock-out punch.

**Why:** Without both punches the hours worked cannot be known, and payroll would either
underpay or overpay the worker.

**How it is checked:** A shift with an "in" punch but no matching "out" punch (or the
reverse) is a missed punch. A shift is still open only while it is in progress: a missing
clock-out is flagged once 4 hours have passed after the scheduled shift end (or, for an
unscheduled shift, once the maximum shift length in P15 has passed since the clock-in).

**Allowed fixes:** Add the missing punch at the time the worker confirms, or at the
scheduled shift end if the worker confirms they left on time. The supervisor must approve.
The worker is asked first.
If the worker does not reply in time, the supervisor may decide on the evidence.

## P2: Duplicate punches are merged

**Rule:** Two punches of the same type by the same worker within 5 minutes of each other
count as one punch.

**Why:** Workers often tap twice when a device is slow. The extra punch is noise, not work.

**How it is checked:** Same worker, same punch type, timestamps no more than 5 minutes apart.

**Allowed fixes:** Keep the earliest punch and void the later one. This case is
auto-resolved and audit-logged; no approval is needed.

## P3: Maximum hours per day

**Rule:** A worker may not work more than 9 hours in a single day (breaks excluded).

**Why:** Long days raise injury risk in the warehouse and break labour rules.

**How it is checked:** Worked hours for the shift date are the time between clock-in and
clock-out, minus breaks. More than 9 hours is a breach.

**Allowed fixes:** The supervisor confirms the extra hours were authorised (they stay as
overtime) or corrects a wrong punch. Hours are never removed without the worker being told.
If the worker does not reply in time, the supervisor may decide on the evidence.

## P4: Break required on long shifts

**Rule:** A worker who works more than 5 hours in a shift must take a break of at least
30 minutes.

**Why:** Rest breaks are a legal requirement and reduce fatigue errors.

**How it is checked:** If worked time exceeds 5 hours and the recorded breaks add up to
less than 30 minutes, the shift breaches this policy.

**Allowed fixes:** If the worker confirms they took a break but did not punch it, add the
break punches as confirmed. If no break was taken, the supervisor records the breach and
notes follow-up. Missed breaks are never hidden.
If the worker does not reply in time, the supervisor may decide on the evidence.

## P5: Weekly overtime threshold

**Rule:** Hours worked above 40 hours in a Monday-to-Sunday week are overtime and need
supervisor approval.

**Why:** Overtime costs more and must be planned. Spotting it early lets the supervisor
adjust the rota before it happens.

**How it is checked:** Hours already worked this week plus hours still scheduled this week.
If the total is above 40 hours, the system raises an overtime risk before the week ends
(or a breach if the hours already worked are above 40). Hours still scheduled are the
shift length minus a planned 60-minute unpaid lunch for shifts longer than 6 hours, so a
09:00-18:00 shift counts as 8 hours. A past shift with a missing punch counts at its
scheduled hours until it is corrected. Leave is taken out of the schedule first: an
upcoming day with approved or pending full-day leave counts as 0 hours, and a half-day
leave takes 4 hours off that day (see P13).

**Allowed fixes:** Approve the overtime, or shorten or reassign upcoming shifts. Worked
hours in the past are never changed by this policy.

## P6: Minimum rest between shifts

**Rule:** There must be at least 11 hours between the end of one shift and the start of
the next.

**Why:** Short turnarounds cause fatigue and are a safety risk.

**How it is checked:** Time from a clock-out to the next clock-in for the same worker.

**Allowed fixes:** The supervisor records why the short rest happened and adjusts the next
shift if it is still in the future.

## P7: Late arrival grace period

**Rule:** Clocking in up to 10 minutes after the scheduled start is within grace and is not
counted as late. Clocking in more than 10 minutes after the start is a late arrival.
Clocking out more than 10 minutes before the scheduled end is an early leave.

**Why:** Small delays (a queue at the gate) should not create paperwork. Real lateness
should be visible.

**How it is checked:** First clock-in of the shift compared with the scheduled start, and
last clock-out compared with the scheduled end.

**Allowed fixes:** Arrivals within grace are auto-resolved and audit-logged. Late arrivals
beyond grace go to the supervisor, who may accept a reason from the worker. The clock-in
time itself is never moved earlier. Early leave beyond grace is handled the same way.

## P8: Unscheduled work needs approval

**Rule:** Work on a day with no scheduled shift needs supervisor approval to be paid.

**Why:** Unplanned work may be a mistake, a swap that was not recorded, or real extra work.

**How it is checked:** A shift whose punches do not belong to any scheduled shift (see the
matching window in P15). Normally this is a date where the worker has no row in the schedule.

**Allowed fixes:** The supervisor approves the work (for example, a shift swap) or rejects
it after asking the worker. If the day is also a public holiday, this approval comes before
the P14 choice.

## P9: No punches on an approved leave day

**Rule:** A worker on approved full-day leave should have no punches that day. The same
applies to a pending full-day leave request: it must be settled before it is approved.

**Why:** Either the leave or the punches are wrong, and both affect pay and leave balance.

**How it is checked:** Punches on a date with an approved or pending full-day leave record.
Rejected leave is ignored. Half-day leave is handled by P13 instead.

**Allowed fixes:** Cancel the leave (the day becomes a worked day and the balance is
restored) or void the punches if they were made by mistake. The worker is asked first.
If the worker does not reply in time, the supervisor may decide on the evidence.

## P10: Unexplained absence

**Rule:** A scheduled shift with no punches and no leave request is an unexplained absence.

**Why:** Payroll needs to know whether to pay the day, deduct it, or record leave.

**How it is checked:** A scheduled shift with no punches and no leave record of any status,
once its scheduled end plus the P1 grace (4 hours) has passed. This includes a worker on
holiday duty who did not come in.

**Allowed fixes:** Record leave (if the worker applies and has balance), mark as unpaid
absence, or add punches if the worker was present and the device failed. Supervisor approval
is required for every option.

## P11: Leave must be within balance

**Rule:** Leave taken cannot exceed the remaining balance for that leave type. The balance
is the yearly total minus leave already used.

**Why:** Leave beyond balance has to be unpaid or come from another leave type.

**How it is checked:** Requested leave days compared with total minus used for that leave
type. The balance is always calculated, never stored.

**Allowed fixes:** Approve days up to the balance and mark the rest as unpaid leave, or move
the extra days to another leave type that has balance. Supervisor approval is required.

## P12: Long sick leave needs a medical certificate

**Rule:** Sick leave of more than 2 days in a row needs a medical certificate.

**Why:** It confirms the absence is genuine and protects the worker's pay.

**How it is checked:** A run of more than 2 sick-leave days (public holidays and days off in
between do not break the run) where no certificate is uploaded.

**Allowed fixes:** Ask the worker to upload a certificate. Until it arrives, the days stay
pending. The supervisor decides what happens if no certificate is provided.

## P13: Half-day leave means half a day of work

**Rule:** On a half-day leave, the worker is expected to work about 4 hours.

**Why:** Working a full day on a half-day leave means the leave was not needed, or the
punches are wrong.

**How it is checked:** Worked hours on a date with an approved or pending half-day leave,
compared with 4 hours, allowing 1 hour either way. More than 5 hours means the worker
worked a full day. Less than 3 hours (including no punches at all, once the shift is over)
means the working half is missing. Late arrival and early leave (P7) are not checked on a
half-day leave day. A short day with no leave on file is a P7 case, not P13.

**Allowed fixes:** Cancel the half-day leave (restoring the balance) if the worker worked the
full day, or correct the punches. If the working half is missing, record a full day of leave
or unpaid hours. The worker is asked first.
If the worker does not reply in time, the supervisor may decide on the evidence.

## P14: Holiday work earns holiday pay or comp-off

**Rule:** Work on a public holiday earns either holiday pay or a compensatory day off
(comp-off). The supervisor chooses one with the worker.

**Why:** Holiday work must be compensated, and payroll needs to know which option applies.

**How it is checked:** Punches attributed to a national or company holiday in the holiday
calendar (optional holidays do not count). Because of P15, a night shift that started the
day before a holiday and ends on the holiday is not holiday work. Planned holiday duty (the
worker was scheduled) is low severity. Unscheduled holiday work is medium severity.

**Allowed fixes:** Choose holiday pay or comp-off. Comp-off is a full day, or half a day
when 4 hours or less were worked. If the work was also unscheduled, P8 must be approved
first. If a punch is missing (P1), fix it first so the hours are known.

## P15: Night shifts belong to the date they started

**Rule:** A shift that crosses midnight belongs entirely to the date it started.

**Why:** It keeps daily hours, holiday checks and absence checks correct for night workers.

**How it is checked:** This is an attribution rule, not an exception. The engine uses it
when grouping punches into shifts. A correct night shift must never be flagged as a missed
punch, an absence or holiday work just because it crosses midnight. A punch belongs to a
scheduled shift if it falls between 4 hours before the scheduled start and 6 hours after the
scheduled end. Punches outside any scheduled shift are grouped from clock-in to clock-out,
and no shift is longer than 16 hours.

**Allowed fixes:** None needed. It shapes how other policies are checked.

## P16: Maximum consecutive working days

**Rule:** A worker may not work more than 6 days in a row.

**Why:** Workers need regular full days of rest.

**How it is checked:** Count consecutive dates with worked shifts (by P15 attribution).
A 7th consecutive day is a breach. The same check runs on the upcoming schedule to warn in
advance (a risk). Upcoming days with full-day leave do not count, and a day off, a leave
day or a holiday without work ends the run.

**Allowed fixes:** The supervisor gives the worker a rest day or records an approved
exception.

## P17: Possible punch conflict, needs review

**Rule:** Punches that look physically impossible or unusual are sent to a person to review
before payroll. This is a check of the data, not an accusation: there is often an innocent
reason (a shared device, a phone with bad GPS, a clock that was wrong).

**Why:** Payroll should only pay for punches that a person has checked when they look odd.

**How it is checked:** Three checks, each raised as "possible punch conflict, needs review":
1. Same second: 2 or more workers punch on the same terminal at exactly the same second
   (mobile app punches are not compared, since each phone is separate).
2. Two places: one worker has two punches at different sites less than 60 minutes apart.
   Gates and app locations are mapped to a site in `policy.json`. All three current
   locations belong to Warehouse 1.
3. App outside the workplace: a mobile app punch whose location is not an approved app
   location. The only approved one today is "Warehouse 1 - Mobile app (geofenced)".

**Allowed fixes:** The supervisor confirms the punches are valid (nothing changes), or, after
asking the worker, voids the punches that were wrong. Nothing is changed automatically.
