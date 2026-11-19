"""The exception status flow. Every status change goes through check_transition().

    open ----------------> awaiting_worker | awaiting_supervisor | resolved | escalated
    awaiting_worker -----> awaiting_supervisor | escalated
    awaiting_supervisor -> resolved | awaiting_worker | escalated
    escalated -----------> awaiting_supervisor | resolved | rejected
    resolved, rejected      final

One exception to "final" (Phase 12): an auto-resolved case may go resolved -> open once,
through action "undo" by a person (cases/service.py undo_auto_resolve). It is checked by
check_transition(..., action="undo") and is not part of ALLOWED.

A supervisor's reject does not end the case: it moves it to `escalated` and assigns it to
the payroll admin. Only a reject by the assignee of an escalated case ends in `rejected`.
"""

from __future__ import annotations

from typing import Literal

from attendflow.errors import InvalidTransitionError

Status = Literal[
    "open", "awaiting_worker", "awaiting_supervisor", "resolved", "rejected", "escalated"
]

ALLOWED: dict[str, frozenset[str]] = {
    "open": frozenset({"awaiting_worker", "awaiting_supervisor", "resolved", "escalated"}),
    "awaiting_worker": frozenset({"awaiting_supervisor", "escalated"}),
    "awaiting_supervisor": frozenset({"resolved", "awaiting_worker", "escalated"}),
    "escalated": frozenset({"awaiting_supervisor", "resolved", "rejected"}),
    "resolved": frozenset(),
    "rejected": frozenset(),
}
FINAL = frozenset(s for s, targets in ALLOWED.items() if not targets)
# Statuses where someone is waiting on a person; waiting_since is set only for these.
WAITING = frozenset({"awaiting_worker", "awaiting_supervisor", "escalated"})


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED.get(current, frozenset())


UNDO = ("resolved", "open")  # only for action "undo" of an auto-resolved case


def check_transition(current: str, target: str, *, action: str | None = None) -> None:
    if can_transition(current, target):
        return
    if action == "undo" and (current, target) == UNDO:
        return
    allowed = sorted(ALLOWED.get(current, frozenset()))
    what = f"{action}: " if action else ""
    if current in FINAL:
        msg = f"{what}the exception is already {current} (final), it cannot change"
    else:
        msg = f"{what}cannot move from {current} to {target}; allowed from {current}: {allowed}"
    raise InvalidTransitionError(msg, details={"from": current, "to": target, "allowed": allowed})
