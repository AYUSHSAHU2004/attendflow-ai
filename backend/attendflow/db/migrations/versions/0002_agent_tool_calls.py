"""Record individual agent tool calls across model steps and runs."""

import sqlalchemy as sa
from alembic import op

revision = "0002_agent_tool_calls"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy rows have no run or timing metadata.
    op.add_column("tool_calls", sa.Column("run_id", sa.String(32), nullable=True))
    op.add_column("tool_calls", sa.Column("call_no", sa.Integer(), nullable=True))
    op.add_column("tool_calls", sa.Column("ok", sa.Boolean(), nullable=True))
    op.add_column("tool_calls", sa.Column("duration_ms", sa.Float(), nullable=True))
    op.alter_column("tool_calls", "tool_name", type_=sa.Text(), existing_type=sa.String(60))
    op.drop_constraint(op.f("uq_tool_calls_exception_id"), "tool_calls", type_="unique")
    op.create_unique_constraint(
        op.f("uq_tool_calls_run_id"), "tool_calls", ["run_id", "step_no", "call_no"]
    )
    op.create_index("ix_tool_calls_exception_id", "tool_calls", ["exception_id"])


def downgrade() -> None:
    # Restore the old constraint first. PostgreSQL rolls back if newer history cannot fit it.
    op.create_unique_constraint(
        op.f("uq_tool_calls_exception_id"), "tool_calls", ["exception_id", "step_no"]
    )
    op.drop_index("ix_tool_calls_exception_id", table_name="tool_calls")
    op.drop_constraint(op.f("uq_tool_calls_run_id"), "tool_calls", type_="unique")
    op.alter_column("tool_calls", "tool_name", type_=sa.String(60), existing_type=sa.Text())
    for column in ("duration_ms", "ok", "call_no", "run_id"):
        op.drop_column("tool_calls", column)
