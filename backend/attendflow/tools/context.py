"""What a tool gets to work with, and the read-only database session that loads it."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cached_property

from sqlalchemy import event, text
from sqlalchemy.orm import Session, sessionmaker

from attendflow.data.loader import Dataset
from attendflow.data.schemas import Employee
from attendflow.engine.engine import build_context
from attendflow.engine.rules import RuleContext, to_minute
from attendflow.engine.shifts import ProcessedPunches
from attendflow.policy.models import PolicyConfig
from attendflow.tools.models import ToolInputError

READ_ONLY = "attendflow_read_only"


class ReadOnlyViolation(RuntimeError):
    pass


@event.listens_for(Session, "before_flush")
def _block_flush(session: Session, flush_context, instances) -> None:  # noqa: ARG001
    if session.info.get(READ_ONLY):
        raise ReadOnlyViolation("this session is read-only: tools never write")


@contextmanager
def read_only_session(factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session whose transaction PostgreSQL itself refuses to write in, plus a flush
    guard in SQLAlchemy. It always rolls back, never commits."""
    session = factory()
    session.info[READ_ONLY] = True
    try:
        session.execute(text("SET TRANSACTION READ ONLY"))
        yield session
    finally:
        session.rollback()
        session.close()


@dataclass
class ToolContext:
    """An in-memory snapshot of the data. Tools only ever see this, never a session."""

    dataset: Dataset
    policy: PolicyConfig
    policy_text: dict[str, str]
    as_of: datetime
    _employees: dict[str, Employee] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._employees = self.dataset.employees_by_id

    def employee(self, employee_id: str) -> Employee:
        emp = self._employees.get(employee_id)
        if emp is None:
            known = ", ".join(sorted(e for e, x in self._employees.items() if x.role == "worker"))
            raise ToolInputError(
                "unknown_employee", f"no employee {employee_id}", hint=f"workers: {known}"
            )
        return emp

    @cached_property
    def _engine(self) -> tuple[RuleContext, ProcessedPunches]:
        return build_context(self.dataset, self.policy, self.as_of)

    @property
    def rules(self) -> RuleContext:
        return self._engine[0]

    @property
    def processed(self) -> ProcessedPunches:
        return self._engine[1]


def fmt_time(ts: datetime, on: date) -> str:
    """'09:00' on the shift date, '2026-04-15 06:00' on another day (night shifts)."""
    ts = to_minute(ts)
    return ts.strftime("%H:%M") if ts.date() == on else ts.strftime("%Y-%m-%d %H:%M")
