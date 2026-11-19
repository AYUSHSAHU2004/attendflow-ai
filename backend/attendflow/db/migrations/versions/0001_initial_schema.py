"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-19 09:57:45.032240
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("employee_id", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("team", sa.String(length=50), nullable=False),
        sa.Column("supervisor_id", sa.String(length=8), nullable=True),
        sa.CheckConstraint(
            "role IN ('worker', 'supervisor', 'payroll_admin')", name=op.f("ck_employees_role")
        ),
        sa.ForeignKeyConstraint(
            ["supervisor_id"],
            ["employees.employee_id"],
            name=op.f("fk_employees_supervisor_id_employees"),
        ),
        sa.PrimaryKeyConstraint("employee_id", name=op.f("pk_employees")),
    )
    op.create_table(
        "holidays",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "type IN ('national', 'company', 'optional')", name=op.f("ck_holidays_type")
        ),
        sa.PrimaryKeyConstraint("date", name=op.f("pk_holidays")),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
    )
    op.create_table(
        "exceptions",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("employee_id", sa.String(length=8), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("policy_id", sa.String(length=4), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=6), nullable=False),
        sa.Column("kind", sa.String(length=6), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("auto_resolved", sa.Boolean(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fix_options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("proposed_fix", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("applied_fix", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("assigned_to", sa.String(length=8), nullable=True),
        sa.Column("waiting_since", sa.DateTime(), nullable=True),
        sa.Column("last_detected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('breach', 'risk')", name=op.f("ck_exceptions_kind")),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high')", name=op.f("ck_exceptions_severity")
        ),
        sa.CheckConstraint(
            "status IN ('open', 'awaiting_worker', 'awaiting_supervisor', 'resolved', 'rejected', 'escalated')",  # noqa: E501
            name=op.f("ck_exceptions_status"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"],
            ["employees.employee_id"],
            name=op.f("fk_exceptions_assigned_to_employees"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.employee_id"],
            name=op.f("fk_exceptions_employee_id_employees"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exceptions")),
    )
    op.create_index("ix_exceptions_employee", "exceptions", ["employee_id"], unique=False)
    op.create_index("ix_exceptions_policy", "exceptions", ["policy_id"], unique=False)
    op.create_index("ix_exceptions_status", "exceptions", ["status"], unique=False)
    op.create_table(
        "leave_balances",
        sa.Column("employee_id", sa.String(length=8), nullable=False),
        sa.Column("leave_type", sa.String(length=10), nullable=False),
        sa.Column("total_per_year", sa.Float(), nullable=False),
        sa.Column("used", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.employee_id"],
            name=op.f("fk_leave_balances_employee_id_employees"),
        ),
        sa.PrimaryKeyConstraint("employee_id", "leave_type", name=op.f("pk_leave_balances")),
    )
    op.create_table(
        "leave_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.String(length=8), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("leave_type", sa.String(length=10), nullable=False),
        sa.Column("duration", sa.String(length=4), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("certificate_uploaded", sa.Boolean(), nullable=False),
        sa.Column("unpaid", sa.Boolean(), nullable=False),
        sa.CheckConstraint("duration IN ('full', 'half')", name=op.f("ck_leave_records_duration")),
        sa.CheckConstraint(
            "leave_type IN ('sick', 'casual', 'earned')", name=op.f("ck_leave_records_leave_type")
        ),
        sa.CheckConstraint(
            "status IN ('approved', 'pending', 'rejected')", name=op.f("ck_leave_records_status")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.employee_id"],
            name=op.f("fk_leave_records_employee_id_employees"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_records")),
        sa.UniqueConstraint("employee_id", "date", name=op.f("uq_leave_records_employee_id")),
    )
    op.create_table(
        "schedule",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.String(length=8), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("shift_start", sa.Time(), nullable=False),
        sa.Column("shift_end", sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.employee_id"],
            name=op.f("fk_schedule_employee_id_employees"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedule")),
        sa.UniqueConstraint("employee_id", "date", name=op.f("uq_schedule_employee_id")),
    )
    op.create_table(
        "timecards",
        sa.Column("punch_id", sa.String(length=16), nullable=False),
        sa.Column("employee_id", sa.String(length=8), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("type", sa.String(length=12), nullable=False),
        sa.Column("source", sa.String(length=12), nullable=False),
        sa.Column("device_id", sa.String(length=50), nullable=False),
        sa.Column("location", sa.String(length=100), nullable=False),
        sa.Column("voided", sa.Boolean(), nullable=False),
        sa.Column("voided_by_exception", sa.String(length=80), nullable=True),
        sa.Column("created_by_exception", sa.String(length=80), nullable=True),
        sa.CheckConstraint(
            "source IN ('device', 'app', 'correction')", name=op.f("ck_timecards_source")
        ),
        sa.CheckConstraint(
            "type IN ('in', 'out', 'break_start', 'break_end')", name=op.f("ck_timecards_type")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.employee_id"],
            name=op.f("fk_timecards_employee_id_employees"),
        ),
        sa.PrimaryKeyConstraint("punch_id", name=op.f("pk_timecards")),
    )
    op.create_index(
        "ix_timecards_employee_ts", "timecards", ["employee_id", "timestamp"], unique=False
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exception_id", sa.String(length=80), nullable=True),
        sa.Column("actor", sa.String(length=12), nullable=False),
        sa.Column("actor_id", sa.String(length=8), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "actor IN ('system', 'agent', 'worker', 'supervisor', 'admin')",
            name=op.f("ck_audit_log_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["exception_id"], ["exceptions.id"], name=op.f("fk_audit_log_exception_id_exceptions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_log_exception", "audit_log", ["exception_id"], unique=False)
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exception_id", sa.String(length=80), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=60), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["exception_id"], ["exceptions.id"], name=op.f("fk_tool_calls_exception_id_exceptions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_calls")),
        sa.UniqueConstraint("exception_id", "step_no", name=op.f("uq_tool_calls_exception_id")),
    )


def downgrade() -> None:
    op.drop_table("tool_calls")
    op.drop_index("ix_audit_log_exception", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_timecards_employee_ts", table_name="timecards")
    op.drop_table("timecards")
    op.drop_table("schedule")
    op.drop_table("leave_records")
    op.drop_table("leave_balances")
    op.drop_index("ix_exceptions_status", table_name="exceptions")
    op.drop_index("ix_exceptions_policy", table_name="exceptions")
    op.drop_index("ix_exceptions_employee", table_name="exceptions")
    op.drop_table("exceptions")
    op.drop_table("settings")
    op.drop_table("holidays")
    op.drop_table("employees")
