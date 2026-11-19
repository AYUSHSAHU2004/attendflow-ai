"""Entry point of the deterministic rule engine. No LLM is involved anywhere here."""

from __future__ import annotations

from datetime import datetime

from attendflow.data.loader import Dataset
from attendflow.engine.checks import CHECKS
from attendflow.engine.models import EngineResult
from attendflow.engine.rules import RuleContext
from attendflow.engine.shifts import process_punches
from attendflow.policy.models import PolicyConfig


def _policy_number(policy_id: str) -> int:
    return int(policy_id.removeprefix("P"))


def run_engine(
    dataset: Dataset,
    policy: PolicyConfig,
    as_of: datetime,
    policies: list[str] | None = None,
) -> EngineResult:
    """Group punches into shifts and run every policy check.

    `policies` limits which checks run (default: all implemented ones). The result is
    fully deterministic: same data + same policy + same as-of time -> same output.
    """
    if as_of.tzinfo is not None:
        raise ValueError("as_of must be a plain local time (no timezone)")
    processed = process_punches(dataset, policy, as_of)
    workers = {e.employee_id for e in dataset.employees if e.role == "worker"}
    # Building the context also applies leave to the schedule (stage 1, see checks.py).
    ctx = RuleContext(
        policy=policy,
        as_of=as_of,
        shifts=processed.shifts,
        schedule=[r for r in dataset.schedule if r.employee_id in workers],
        duplicate_runs=processed.duplicate_runs,
        leave_records=[r for r in dataset.leave_records if r.employee_id in workers],
        leave_balances=[b for b in dataset.leave_balances if b.employee_id in workers],
        holidays=list(dataset.holidays),
        punches=[p for p in dataset.punches if p.employee_id in workers and p.timestamp <= as_of],
    )
    selected = policies or list(CHECKS)
    unknown = [p for p in selected if p not in CHECKS]
    if unknown:
        raise ValueError(f"no check implemented for {unknown}")

    exceptions = [exc for pid in selected for exc in CHECKS[pid](ctx)]
    exceptions.sort(
        key=lambda e: (e.employee_id, e.date, _policy_number(e.policy_id), e.exception_id)
    )
    return EngineResult(
        as_of=as_of,
        policy_version=policy.version,
        shifts=processed.shifts,
        exceptions=exceptions,
        voided_punch_ids=sorted(p.punch_id for r in processed.duplicate_runs for p in r.voided),
        ignored_future_punches=processed.ignored_future_punches,
    )
