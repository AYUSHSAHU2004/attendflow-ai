"""Store the latest investigation and persist investigation jobs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_investigations"
down_revision = "0002_agent_tool_calls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exceptions", sa.Column("investigation_case", postgresql.JSONB(), nullable=True))
    op.create_table(
        "investigation_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("exception_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("reason", sa.String(40), nullable=True),
        sa.ForeignKeyConstraint(
            ["exception_id"],
            ["exceptions.id"],
            name=op.f("fk_investigation_jobs_exception_id_exceptions"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name=op.f("ck_investigation_jobs_status"),
        ),
    )
    op.create_index(
        "ix_investigation_jobs_active_exception",
        "investigation_jobs",
        ["exception_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_table("investigation_jobs")
    op.drop_column("exceptions", "investigation_case")
