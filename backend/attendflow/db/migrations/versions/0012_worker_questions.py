"""Phase 20: questions workers asked the employee Q&A, and the answers shown."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_worker_questions"
down_revision = "0011_no_reply_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.String(8), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("intents", postgresql.JSONB(), nullable=False),
        sa.Column("plan_source", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("refusal_code", sa.String(20), nullable=True),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("facts_hash", sa.String(64), nullable=True),
        sa.Column("attempts", postgresql.JSONB(), nullable=False),
        sa.Column("llm_calls", sa.SmallInteger(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("workflow_at", sa.DateTime(), nullable=False),
        sa.Column("created_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('answer', 'refusal')", name=op.f("ck_worker_questions_kind")),
        sa.CheckConstraint(
            "source IN ('llm', 'template', 'refusal')", name=op.f("ck_worker_questions_source")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.employee_id"],
            name=op.f("fk_worker_questions_employee_id_employees"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_questions")),
    )
    op.create_index("ix_worker_questions_employee_id", "worker_questions", ["employee_id", "id"])
    op.create_index("ix_worker_questions_created_utc", "worker_questions", ["created_utc"])


def downgrade() -> None:
    op.drop_index("ix_worker_questions_created_utc", table_name="worker_questions")
    op.drop_index("ix_worker_questions_employee_id", table_name="worker_questions")
    op.drop_table("worker_questions")
