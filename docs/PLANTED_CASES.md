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

## Policies not planted in this week

**P6** (rest between shifts) and **P16** (consecutive days) have no planted breach. The
engine tests in later phases will use small synthetic fixtures for them.
