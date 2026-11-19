# Planted cases (demo ground truth)

This is the answer key for the rule engine. Each case below is planted in `data/*.csv` by
`backend/attendflow/scripts/generate_data.py`. Tests in `tests/test_planted_cases.py`
check that the data really contains each case.

- **Demo week:** Mon 13 Apr to Sun 19 Apr 2026.
- **Holiday:** Tue 14 Apr 2026, Ambedkar Jayanti (national). Most staff are off.
  Amit and Meena are on the holiday-duty roster (scheduled that day).
- **As-of ("now"):** Thu 16 Apr 2026, 08:00. No punches exist after it. Schedule rows
  after it (Thu, Fri) are the forecast.
- **Standard day shift:** 09:00 to 18:00 with a 1-hour lunch, so 8 hours worked.
- **Teams:** Inbound (supervisor Ravi Kumar, E101): Amit, Meena, Neha, Sana, Arjun.
  Outbound (supervisor Sunita Rao, E102): Ramesh, Karan, Dev, Farah, Pooja.
  Payroll admin: Priya Sharma (E201).

## Expected exceptions

| # | Employee | Date | What the data shows | Expected policy | Notes |
|---|---|---|---|---|---|
| 1 | Amit Verma (E001) | Tue 14 Apr | Clock-in 09:00, lunch break punched, **no clock-out** (shift 09:00-18:00) | **P1** | Also **P14**: he is on holiday duty, so holiday pay or comp-off must be chosen. |
| 2 | Meena Iyer (E002) | Mon-Wed 13-15 Apr | 12 h worked each day = **36 h**; Thu and Fri scheduled 09:00-15:00 = **12 h more** | **P5** (overtime risk, forecast 48 h > 40 h) | Side effects: **P3** on Mon, Tue and Wed (12 h > 9 h), and **P14** on Tue (holiday duty). Rest between shifts is 11.5 h, so **no P6**. |
| 3 | Ramesh Patil (E003) | Mon 13 and Wed 15 Apr | Night shifts 21:58 to 06:00 next day, with break | **None** | Must NOT be flagged. By **P15** each shift belongs to its start date. Monday's shift ends on the holiday morning but is **not** holiday work (no P14). No P1, P3, P8 or P10. |
| 4 | Neha Gupta (E004) | Mon 13 Apr | Shift 09:00-15:00, punched 09:00-15:00, **no break** (6 h > 5 h) | **P4** | |
| 5 | Neha Gupta (E004) | Wed 15 Apr | Scheduled 09:00-18:00, **no punches, no leave** | **P10** | |
| 6 | Sana Khan (E005) | Mon 13 Apr | Two clock-ins at 08:57 and 08:59 (**2 min apart**, same device) | **P2** (auto-resolve) | Keep 08:57, void 08:59, audit-log it. |
| 7 | Sana Khan (E005) | Tue 14 Apr | Punched 10:00-14:00 on the **holiday**, not scheduled | **P14** and **P8** | 4 h, so no break needed (no P4). |
| 8 | Karan Mehta (E006) | Mon 13 Apr | Clock-in **10:30** for a 09:00 shift (90 min late > 10 min grace) | **P7** (not auto-resolved) | |
| 9 | Karan Mehta (E006) | Wed 15 Apr | **Approved full-day casual leave**, but punched 08:58-18:00 | **P9** | |
| 10 | Dev Malhotra (E007) | Mon 13, Wed 15, Thu 16 Apr | **3 sick-leave days**, status pending, **no certificate**. Sick balance = 12 total - 11 used = **1** | **P11** and **P12** | The holiday on Tue does not break the sick-leave run. **No P10**: a leave request exists. |
| 11 | Farah Ali (E008) | Wed 15 Apr | **Approved half-day casual leave**, but punched 08:59-18:01 (~8 h) | **P13** | **Not P9**: P9 covers full-day leave only. |

## Controls (must produce zero exceptions)

| Employee | Why it is there |
|---|---|
| Arjun Nair (E009) | Clean Mon and Wed. Wednesday punches come from the mobile app (`source=app`). |
| Pooja Singh (E010) | Clean Monday. **Approved full-day earned leave** on Wednesday with no punches: no P9 and no P10. |
| Farah Ali (E008), Mon | Clean day. |
| Sana Khan (E005), Wed | Clean day. |
| Amit Verma (E001), Mon and Wed | Clean days, worked exactly 8 h each. His forecast week is 40 h, which is **not** over the P5 limit. |
| Everyone, Thu-Fri | Future (after as-of). Must not be flagged as absences. |
| Ravi, Sunita, Priya | No schedule or punches. Not workers, so never flagged. |

## Full engine output (Phase 2)

`attendflow-detect` on the demo data gives exactly **17 exceptions** (16 open, 1
auto-resolved): the 11 cases above plus their documented side effects.

| Employee | Policies |
|---|---|
| Amit (E001) | P1 Tue, P14 Tue (low: planned holiday duty, fix P1 first) |
| Meena (E002) | P3 Mon/Tue/Wed, P5 week (risk), P14 Tue (low) |
| Neha (E004) | P4 Mon, P10 Wed |
| Sana (E005) | P2 Mon (auto-resolved), P8 Tue, P14 Tue (medium: unscheduled, approve P8 first) |
| Karan (E006) | P7 Mon, P9 Wed |
| Dev (E007) | P11 ("applied 3, balance 1"), P12 (3 days, no certificate), both dated Mon |
| Farah (E008) | P13 Wed (8.03 h on a half-day leave) |

Dev's P5 forecast leaves out his sick Thursday (0 h), so his week counts only Fri (8 h).

## Punch timestamps carry seconds

Each worker has one fixed seconds offset (0 to -29 s) on all of their punches, set in the
generator. Durations and lateness stay exactly as planted, punch IDs do not change, and
times shown rounded to the minute still read as planted (Sana 08:57 / 08:59). No two workers
punch on the same terminal at the same second, so P17 stays quiet on the demo data. Amit
and Karan keep :00 (different gates).

## Policies not planted in this week

**P6** (rest between shifts), **P16** (consecutive days) and **P17** (possible punch
conflict) have no planted case. They are tested with small synthetic fixtures in
`tests/test_engine_rules.py` and `tests/test_engine_rules_phase2.py`.
