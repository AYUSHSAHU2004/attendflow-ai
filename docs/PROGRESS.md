# Progress log

## Phase 0: Project setup, sample data, policy files, LLM test (2026-11-19)

**Built**
- Repo skeleton (`backend/`, `frontend/`, `data/`, `docs/`, `tests/`), README, `.env.example`,
  git-ignored `.env`, and a GitHub Actions CI workflow (lint, data validation, tests).
- Python package `attendflow` (Python 3.12, managed with uv):
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
- Demo data: 10 workers in 2 teams, plus Ravi, Sunita (supervisors) and Priya (payroll).
  All 8 planted cases plus controls are in [PLANTED_CASES.md](PLANTED_CASES.md).
- `data/policy.json` (limits) and `data/policy.md` (plain-language policy, one section per ID).
- 46 tests: validation failure modes, policy integrity, planted-case fixtures and the LLM
  client using a fake client.

**Decisions**
- Demo week Mon 13 to Sun 19 Apr 2026, with the holiday on Tue 14 Apr (Ambedkar Jayanti).
  The as-of time is Thu 16 Apr 08:00, so Meena's overtime is a forecast, not a breach.
- Amit and Meena are on the holiday-duty roster. So Amit also gets P14, and Meena also gets
  P3 (12 h days) and P14. These are documented as expected.
- The data is produced by a deterministic generator. A test fails if anyone edits a CSV by
  hand without updating the generator.
- `validate` also checks that every numeric limit in `policy.json` appears in `policy.md`,
  so the text the agent cites cannot drift from the limit the code enforces.
- **LLM changed from Llama 3.3 70B to `openai/gpt-oss-120b` (Apache 2.0).** Groq retired
  Llama 3.3, and the user chose this model. See [LLM_LICENCE.md](LLM_LICENCE.md).

**Next (Phase 1)**
- Deterministic rule engine: group punches into shifts (P15), compute hours, and detect
  P1-P16 using `policy.json` limits only. Check it against PLANTED_CASES.md as the
  expected output.
