"""Store worker time review, the asked proposal, and a confirmed re-check."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_worker_time"
down_revision = "0004_worker_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("worker_messages", sa.Column("asked_fix", JSONB(), nullable=True))
    op.add_column("worker_messages", sa.Column("time_review", JSONB(), nullable=True))
    op.add_column("exceptions", sa.Column("worker_recheck", JSONB(), nullable=True))

    op.execute("""
        UPDATE worker_messages AS m
        SET time_review = jsonb_build_object('stage', 'manual', 'approximate', false)
        FROM exceptions AS e
        WHERE m.exception_id = e.id AND m.recipient_id = e.assigned_to
          AND m.needs_actual_time AND e.status = 'awaiting_worker'
          AND ((e.policy_id = 'P1' AND e.fix_options @> '[{"action":"set_clock_out"}]'::jsonb)
            OR (e.policy_id = 'P3' AND e.fix_options @> '[{"action":"correct_clock_out"}]'::jsonb))
    """)


def downgrade() -> None:
    op.drop_column("exceptions", "worker_recheck")
    op.drop_column("worker_messages", "time_review")
    op.drop_column("worker_messages", "asked_fix")
