"""Current payroll readiness sign-off. The audit log preserves every decision."""

import sqlalchemy as sa
from alembic import op

revision = "0009_payroll_signoffs"
down_revision = "0008_no_reply_ladder"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_signoffs",
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("signed_by", sa.String(8), nullable=False),
        sa.Column("signer_name", sa.Text(), nullable=False),
        sa.Column("signed_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("reopened_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["signed_by"],
            ["employees.employee_id"],
            name=op.f("fk_payroll_signoffs_signed_by_employees"),
        ),
        sa.PrimaryKeyConstraint("week_start", name=op.f("pk_payroll_signoffs")),
    )


def downgrade() -> None:
    op.drop_table("payroll_signoffs")
