"""Phase 14 anti-drift guard: every audit row any test writes must be in the Autonomy Table.

conftest.py listens to every AuditLogRow insert for the whole session. An insert whose
(action, actor) pair no registry row covers is recorded here, and the test that wrote it
fails in teardown, so a new audit action can never ship without its Autonomy Table row.
"""

from __future__ import annotations

from collections import Counter

UNMAPPED: list[tuple[str, str]] = []
SEEN: Counter[tuple[str, str]] = Counter()


def record(mapper, connection, target) -> None:  # SQLAlchemy before_insert signature
    from attendflow.activity.autonomy import capability_for

    pair = (target.action, target.actor)
    SEEN[pair] += 1
    if capability_for(target.action, target.actor) is None:
        UNMAPPED.append(pair)
