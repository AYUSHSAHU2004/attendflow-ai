"""Persisted job lifecycle, expiration and restart recovery."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from attendflow.agent.case import (
    InvestigationCase,
    fallback_case,
    normalized_params,
    routing,
)
from attendflow.agent.structured import investigate
from attendflow.clock import Clock
from attendflow.config import Settings
from attendflow.db.models import AuditLogRow, EmployeeRow, ExceptionRow, InvestigationJobRow
from attendflow.errors import ForbiddenError, NotFoundError
from attendflow.policy.models import load_policy_text

log = logging.getLogger("attendflow.investigation")


def authorized_case(
    session: Session, exception_id: str, actor_id: str, *, lock: bool = False
) -> ExceptionRow:
    row = session.get(ExceptionRow, exception_id, with_for_update=lock)
    if row is None:
        raise NotFoundError(f"exception {exception_id} not found", code="exception_not_found")
    actor = session.get(EmployeeRow, actor_id)
    if actor is None:
        raise ForbiddenError(f"unknown actor {actor_id}", code="unknown_actor")
    if actor.role != "payroll_admin" and (
        actor.role != "supervisor" or row.assigned_to != actor_id
    ):
        raise ForbiddenError(
            "only payroll or the assigned supervisor can investigate", code="not_assigned"
        )
    return row


@dataclass
class InvestigationJobs:
    sessions: sessionmaker[Session]
    settings: Settings
    clock: Clock

    def start(self, exception_id: str, actor: str) -> tuple[InvestigationJobRow, bool]:
        with self.sessions.begin() as session:
            row = authorized_case(session, exception_id, actor, lock=True)
            existing = session.scalar(
                select(InvestigationJobRow).where(
                    InvestigationJobRow.exception_id == row.id,
                    InvestigationJobRow.status == "running",
                )
            )
            if existing is not None:
                return existing, False
            now = datetime.now(UTC)
            job = InvestigationJobRow(
                id=uuid4().hex,
                exception_id=row.id,
                status="running",
                started_at=now,
                deadline_at=now + timedelta(seconds=self.settings.llm_investigation_budget_seconds),
            )
            session.add(job)
            return job, True

    def get(self, exception_id: str, job_id: str, actor: str) -> InvestigationJobRow:
        with self.sessions() as session:
            authorized_case(session, exception_id, actor)
            job = session.get(InvestigationJobRow, job_id)
            if job is None or job.exception_id != exception_id:
                raise NotFoundError(
                    "investigation job not found", code="investigation_job_not_found"
                )
        return job

    def run(self, job_id: str) -> None:
        with self.sessions() as session:
            job = session.get(InvestigationJobRow, job_id)
            if job is None or job.status != "running":
                return
            remaining = (job.deadline_at - datetime.now(UTC)).total_seconds()
            exception_id = job.exception_id
        if remaining <= 0:
            self.finish(job_id, "deadline_exceeded")
            return
        try:
            result = investigate(
                exception_id,
                self.settings,
                self.sessions,
                self.clock,
                deadline=time.monotonic() + remaining,
            )
        except Exception:
            log.exception("investigation job failed", extra={"job_id": job_id})
            self.finish(job_id, "job_error")
            return
        self.finish(job_id, result.reason, result.case, result.run_id)

    def recover(self, *, startup: bool = False) -> None:
        query = select(InvestigationJobRow.id).where(InvestigationJobRow.status == "running")
        if not startup:
            query = query.where(InvestigationJobRow.deadline_at <= datetime.now(UTC))
        with self.sessions() as session:
            ids = list(session.scalars(query))
        for job_id in ids:
            self.finish(job_id, "api_restarted" if startup else "deadline_exceeded")

    def finish(
        self,
        job_id: str,
        reason: str,
        case: InvestigationCase | None = None,
        run_id: str | None = None,
    ) -> None:
        with self.sessions.begin() as session:
            job = session.get(InvestigationJobRow, job_id, with_for_update=True)
            if job is None or job.status != "running":
                return
            row = session.get(ExceptionRow, job.exception_id, with_for_update=True)
            if row is None:
                return
            now = datetime.now(UTC)
            duration = max(0, (now - job.started_at).total_seconds() * 1000)
            if now >= job.deadline_at and reason != "api_restarted":
                reason = "deadline_exceeded"
            failed = reason in {"deadline_exceeded", "api_restarted", "job_error"}
            if case is not None and case.proposed_fix is not None and not failed:
                proposal = case.proposed_fix
                option = next(
                    (o for o in row.fix_options if o["option_id"] == proposal.option_id), None
                )
                if option is None or normalized_params(option, option["params"]) != proposal.params:
                    reason, case = "case_changed", None
            if case is None or failed:
                policy = load_policy_text(self.settings.data_dir / "policy.md")[row.policy_id]
                case = fallback_case(row, policy, duration, case.tool_steps if case else 0)
            else:
                option = next(
                    (
                        o
                        for o in row.fix_options
                        if case.proposed_fix and o["option_id"] == case.proposed_fix.option_id
                    ),
                    None,
                )
                who, next_action = routing(row, option)
                case = case.model_copy(
                    update={"duration_ms": duration, "who_to_ask": who, "next_action": next_action}
                )
            row.investigation_case = case.model_dump(mode="json")
            row.proposed_fix = (
                case.proposed_fix.model_dump(mode="json") if case.proposed_fix else None
            )
            job.status = "failed" if failed else "completed"
            job.reason = reason
            job.finished_at = now
            job.duration_ms = duration
            session.add(
                AuditLogRow(
                    exception_id=row.id,
                    actor="agent",
                    action="investigation_case_stored",
                    after={
                        "job_id": job.id,
                        "run_id": run_id,
                        "fallback": case.fallback,
                        "duration_ms": duration,
                        "reason": reason,
                    },
                    created_at=self.clock.now(),
                )
            )
        log.info(
            "investigation job finished",
            extra={
                "event": "investigation_job_finished",
                "job_id": job_id,
                "duration_ms": duration,
                "reason": reason,
                "fallback": case.fallback,
            },
        )
