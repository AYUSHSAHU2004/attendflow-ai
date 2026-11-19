"""The investigation's write boundary. Only audit and tool call rows are inserted."""

from sqlalchemy.orm import Session, sessionmaker

from attendflow.clock import FixedClock
from attendflow.db.models import AuditLogRow, ToolCallRow
from attendflow.tools.runner import ToolCallEvent


class RunJournal:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        clock: FixedClock,
        exception_id: str,
        run_id: str,
    ):
        self.sessions = sessions
        self.clock = clock
        self.exception_id = exception_id
        self.run_id = run_id

    def audit(self, action: str, **details: object) -> None:
        with self.sessions.begin() as session:
            session.add(
                AuditLogRow(
                    exception_id=self.exception_id,
                    actor="agent",
                    action=action,
                    after={"run_id": self.run_id, **details},
                    created_at=self.clock.now(),
                )
            )

    def tool_call(self, step_no: int, call_no: int, event: ToolCallEvent) -> None:
        with self.sessions.begin() as session:
            session.add(
                ToolCallRow(
                    exception_id=self.exception_id,
                    run_id=self.run_id,
                    step_no=step_no,
                    call_no=call_no,
                    tool_name=event.name,
                    input=(
                        event.arguments
                        if isinstance(event.arguments, dict)
                        else {"raw_arguments": event.arguments}
                    ),
                    output=event.output,
                    ok=event.ok,
                    duration_ms=event.duration_ms,
                    created_at=self.clock.now(),
                )
            )
