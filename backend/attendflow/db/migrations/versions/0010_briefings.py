"""Phase 17: stored daily briefings (LLM or template), one row per generation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_briefings"
down_revision = "0009_payroll_signoffs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "briefings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(8), nullable=False),
        sa.Column("facts_hash", sa.String(64), nullable=False),
        sa.Column("facts", postgresql.JSONB(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("attempts", postgresql.JSONB(), nullable=False),
        sa.Column("llm_calls", sa.SmallInteger(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("trigger", sa.String(10), nullable=False),
        sa.Column("requested_by", sa.String(8), nullable=True),
        sa.Column("workflow_at", sa.DateTime(), nullable=False),
        sa.Column("created_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source IN ('llm', 'template')", name=op.f("ck_briefings_source")),
        sa.CheckConstraint(
            "trigger IN ('refresh', 'scheduler')", name=op.f("ck_briefings_trigger")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_briefings")),
    )
    op.create_index("ix_briefings_scope_id", "briefings", ["scope", "id"])


def downgrade() -> None:
    op.drop_index("ix_briefings_scope_id", table_name="briefings")
    op.drop_table("briefings")
