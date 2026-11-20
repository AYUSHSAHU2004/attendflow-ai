"""Employee credentials and revocable sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0013_employee_auth"
down_revision = "0012_worker_questions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("email", sa.String(254), nullable=True))
    op.add_column("employees", sa.Column("password_hash", sa.Text(), nullable=True))
    op.create_index("uq_employees_email_lower", "employees", [sa.text("lower(email)")], unique=True)
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "employee_id",
            sa.String(8),
            sa.ForeignKey("employees.employee_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_employee_id", "auth_sessions", ["employee_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("auth_sessions")
    op.drop_index("uq_employees_email_lower", table_name="employees")
    op.drop_column("employees", "password_hash")
    op.drop_column("employees", "email")
