"""Phase 11: device actor, scheduler cycle table, investigated facts hash."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_device_and_scheduler"
down_revision = "0005_worker_time"
branch_labels = None
depends_on = None

OLD_ACTORS = "actor IN ('system', 'agent', 'worker', 'supervisor', 'admin')"
NEW_ACTORS = "actor IN ('system', 'agent', 'worker', 'supervisor', 'admin', 'device')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_audit_log_actor"), "audit_log", type_="check")
    op.create_check_constraint(op.f("ck_audit_log_actor"), "audit_log", NEW_ACTORS)
    op.add_column(
        "exceptions", sa.Column("investigated_facts_hash", sa.String(length=64), nullable=True)
    )
    op.create_table(
        "scheduler_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trigger", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", JSONB(), nullable=True),
        sa.CheckConstraint(
            "trigger IN ('schedule', 'run_now')", name=op.f("ck_scheduler_runs_trigger")
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')", name=op.f("ck_scheduler_runs_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduler_runs")),
    )


def downgrade() -> None:
    op.drop_table("scheduler_runs")
    op.drop_column("exceptions", "investigated_facts_hash")
    op.execute("DELETE FROM audit_log WHERE actor = 'device'")
    op.drop_constraint(op.f("ck_audit_log_actor"), "audit_log", type_="check")
    op.create_check_constraint(op.f("ck_audit_log_actor"), "audit_log", OLD_ACTORS)
