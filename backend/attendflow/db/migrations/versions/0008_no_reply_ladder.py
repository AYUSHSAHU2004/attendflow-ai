"""Phase 13: the no-reply ladder (stage and the time of each step) and the reminder.

Cases already waiting for the worker get their wait start from the latest question:
the No reply's time if it still needs the actual time, else when it was sent.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_no_reply_ladder"
down_revision = "0007_auto_resolve_undo"
branch_labels = None
depends_on = None

STAMPS = (
    "no_reply_wait_since",
    "no_reply_reminded_at",
    "no_reply_supervisor_at",
    "no_reply_admin_at",
    "no_reply_late_reply_at",
)


def upgrade() -> None:
    op.add_column(
        "exceptions",
        sa.Column("no_reply_stage", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    for name in STAMPS:
        op.add_column("exceptions", sa.Column(name, sa.DateTime(timezone=False), nullable=True))
    op.create_check_constraint(
        op.f("ck_exceptions_no_reply_stage"), "exceptions", "no_reply_stage BETWEEN 0 AND 3"
    )
    op.add_column(
        "worker_messages", sa.Column("reminded_at", sa.DateTime(timezone=False), nullable=True)
    )
    op.add_column("worker_messages", sa.Column("reminder_text", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE exceptions AS e
        SET no_reply_wait_since = COALESCE(
            (SELECT CASE WHEN m.needs_actual_time AND m.replied_at IS NOT NULL
                         THEN m.replied_at ELSE m.sent_at END
             FROM worker_messages AS m
             WHERE m.exception_id = e.id
             ORDER BY m.id DESC
             LIMIT 1),
            e.waiting_since)
        WHERE e.status = 'awaiting_worker'
        """
    )


def downgrade() -> None:
    op.drop_column("worker_messages", "reminder_text")
    op.drop_column("worker_messages", "reminded_at")
    op.drop_constraint(op.f("ck_exceptions_no_reply_stage"), "exceptions", type_="check")
    for name in reversed(STAMPS):
        op.drop_column("exceptions", name)
    op.drop_column("exceptions", "no_reply_stage")
