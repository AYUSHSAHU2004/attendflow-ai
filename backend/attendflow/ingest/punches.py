"""The ONLY code besides fixes/apply.py and the demo seed that writes the timecards table.

It writes one thing: a new device punch, as an INSERT. It never updates, voids or deletes
a punch and never touches schedule or leave. Every punch it writes gets a
`punch_ingested` audit row (actor "device") in the same transaction, so the punch and its
audit row are saved together or not at all. Tests enforce all of this (static import
check and a SQL write hook).

No LLM is involved. Detection after the punch runs separately (cases/service.py
detect_after_punch), so a detection failure can never lose an accepted punch.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from attendflow.clock import Clock, data_as_of
from attendflow.config import Settings
from attendflow.db.models import PUNCH_ID_LOCK, AuditLogRow, EmployeeRow, PunchRow
from attendflow.errors import ConflictError, InvalidInputError
from attendflow.policy.models import PolicyConfig

PunchType = Literal["in", "out", "break_start", "break_end"]
Via = Literal["device_api", "demo_simulator"]
SOURCE = "device"


@dataclass(frozen=True)
class PunchInput:
    employee_id: str
    timestamp: datetime
    type: PunchType
    device_id: str | None = None
    location: str | None = None


def _known_locations(policy: PolicyConfig) -> set[str]:
    return set(policy.mapping("P17", "sites"))


def _default_device(session: Session, employee: EmployeeRow) -> tuple[str, str]:
    """The worker's own latest device punch, else the device most used by their team.
    Read from the data, never hard-coded."""
    own = session.scalars(
        select(PunchRow)
        .where(PunchRow.employee_id == employee.employee_id, PunchRow.source == SOURCE)
        .order_by(PunchRow.timestamp.desc(), PunchRow.punch_id.desc())
        .limit(1)
    ).first()
    if own is not None:
        return own.device_id, own.location
    team = session.execute(
        select(PunchRow.device_id, PunchRow.location)
        .join(EmployeeRow, EmployeeRow.employee_id == PunchRow.employee_id)
        .where(EmployeeRow.team == employee.team, PunchRow.source == SOURCE)
    ).all()
    if not team:
        raise InvalidInputError(
            "no device is known for this worker's team; send device_id and location",
            code="location_required",
        )
    (device, location), _ = Counter((d, loc) for d, loc in team).most_common(1)[0]
    return device, location


def _check(
    session: Session, clock: Clock, settings: Settings, policy: PolicyConfig, punch: PunchInput
) -> EmployeeRow:
    employee = session.get(EmployeeRow, punch.employee_id)
    if employee is None:
        raise InvalidInputError(f"unknown employee {punch.employee_id}", code="unknown_employee")
    if employee.role != "worker":
        raise InvalidInputError(
            f"{punch.employee_id} is not a worker; only worker punches are recorded",
            code="not_a_worker",
        )
    now = data_as_of(clock)  # the data cut-off; the demo clock never moves it
    if punch.timestamp > now:
        raise InvalidInputError(
            f"{punch.timestamp:%a %d %b %H:%M} is after now ({now:%a %d %b %H:%M})",
            code="punch_in_future",
        )
    oldest = now - timedelta(days=settings.device_max_backdate_days)
    if punch.timestamp < oldest:
        raise InvalidInputError(
            f"{punch.timestamp:%a %d %b %H:%M} is more than "
            f"{settings.device_max_backdate_days} days before now",
            code="punch_too_old",
        )
    if punch.location is not None and punch.location not in _known_locations(policy):
        raise InvalidInputError(
            f"unknown location {punch.location!r}",
            code="unknown_location",
            details={"known_locations": sorted(_known_locations(policy))},
        )
    return employee


def ingest_punch(
    session: Session,
    clock: Clock,
    settings: Settings,
    policy: PolicyConfig,
    punch: PunchInput,
    *,
    via: Via,
    requested_by: str | None = None,
) -> dict[str, Any]:
    """Validate and store one device punch plus its audit row, in one transaction.
    Returns the stored punch as plain data."""
    with session.begin():
        employee = _check(session, clock, settings, policy, punch)
        # One writer at a time numbers new punches (shared with fixes/apply.py). Taken
        # before the duplicate check, so two identical requests cannot both pass it.
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": PUNCH_ID_LOCK})
        duplicate = session.scalars(
            select(PunchRow.punch_id).where(
                PunchRow.employee_id == employee.employee_id,
                PunchRow.timestamp == punch.timestamp,
                PunchRow.type == punch.type,
                PunchRow.voided.is_(False),
            )
        ).first()
        if duplicate is not None:
            raise ConflictError(
                f"{employee.employee_id} already has this {punch.type} punch "
                f"({duplicate}, {punch.timestamp:%a %d %b %H:%M:%S})",
                code="duplicate_punch",
                details={"punch_id": duplicate},
            )
        device_id, location = punch.device_id, punch.location
        if device_id is None or location is None:
            default_device, default_location = _default_device(session, employee)
            device_id = device_id or default_device
            location = location or default_location
        ids = session.scalars(select(PunchRow.punch_id)).all()
        next_no = max((int(i.removeprefix("P")) for i in ids), default=0) + 1
        row = PunchRow(
            punch_id=f"P{next_no:04d}",
            employee_id=employee.employee_id,
            timestamp=punch.timestamp,
            type=punch.type,
            source=SOURCE,
            device_id=device_id,
            location=location,
            voided=False,
        )
        session.add(row)
        session.flush()
        stored = {
            "punch_id": row.punch_id,
            "employee_id": row.employee_id,
            "timestamp": row.timestamp.isoformat(timespec="seconds"),
            "type": row.type,
            "source": row.source,
            "device_id": row.device_id,
            "location": row.location,
        }
        session.add(
            AuditLogRow(
                exception_id=None,
                actor="device",
                actor_id=None,
                action="punch_ingested",
                after={**stored, "via": via, "requested_by": requested_by},
                created_at=clock.now(),
            )
        )
    return stored
