"""Persist worker questions and replies."""

import sqlalchemy as sa
from alembic import op

revision = "0004_worker_messages"
down_revision = "0003_investigations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("exception_id", sa.String(80), nullable=False),
        sa.Column("recipient_id", sa.String(8), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("reply_prompt", sa.Text(), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=True),
        sa.Column("reply_text", sa.Text(), nullable=True),
        sa.Column("replied_at", sa.DateTime(), nullable=True),
        sa.Column("needs_actual_time", sa.Boolean(), nullable=False),
        sa.CheckConstraint("source IN ('llm', 'template')", name=op.f("ck_worker_messages_source")),
        sa.ForeignKeyConstraint(
            ["exception_id"],
            ["exceptions.id"],
            name=op.f("fk_worker_messages_exception_id_exceptions"),
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["employees.employee_id"],
            name=op.f("fk_worker_messages_recipient_id_employees"),
        ),
    )
    op.create_index("ix_worker_messages_recipient_id", "worker_messages", ["recipient_id"])
    op.create_index("ix_worker_messages_exception_id", "worker_messages", ["exception_id"])
    # Older versions could hand off a case without recording its question.
    op.execute("""
        INSERT INTO worker_messages
            (exception_id, recipient_id, date, message, reply_prompt,
             source, sent_at, needs_actual_time)
        SELECT id, employee_id, date,
            'We need to check your attendance on ' || to_char(date, 'YYYY-MM-DD') ||
                '. Was your recorded attendance correct?',
            'What happened, and what should we know?', 'template',
            COALESCE(waiting_since, updated_at), false
        FROM exceptions
        WHERE status = 'awaiting_worker' AND assigned_to = employee_id
    """)


def downgrade() -> None:
    op.drop_table("worker_messages")
