"""Phase 18: the no-reply ladder limits stored on each case when its wait begins.

Runtime settings (Phase 18) let the payroll admin change the ladder hours. A change must
never re-time a wait that is already running, so each wait keeps the limits it started
with. Cases already in a wait (waiting for the worker, or brought to the supervisor by
the ladder) get the limits in force today: the NO_REPLY_*_HOURS environment values, else
the documented defaults (8, 24, 24). Runtime overrides did not exist before this
migration, so the environment is the whole truth here.
"""

import json
import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_no_reply_limits"
down_revision = "0010_briefings"
branch_labels = None
depends_on = None


def _hours(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    return float(raw) if raw else default


def upgrade() -> None:
    op.add_column("exceptions", sa.Column("no_reply_limits", postgresql.JSONB(), nullable=True))
    limits = {
        "reminder_hours": _hours("NO_REPLY_REMINDER_HOURS", 8),
        "supervisor_hours": _hours("NO_REPLY_SUPERVISOR_HOURS", 24),
        "admin_hours": _hours("NO_REPLY_ADMIN_HOURS", 24),
    }
    op.get_bind().execute(
        sa.text(
            """
            UPDATE exceptions
            SET no_reply_limits = CAST(:limits AS JSONB)
            WHERE status = 'awaiting_worker'
               OR (status = 'awaiting_supervisor' AND no_reply_stage = 2)
            """
        ),
        {"limits": json.dumps(limits)},
    )


def downgrade() -> None:
    op.drop_column("exceptions", "no_reply_limits")
