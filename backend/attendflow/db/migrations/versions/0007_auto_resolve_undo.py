"""Phase 12: who undid an auto-resolve, and when."""

import sqlalchemy as sa
from alembic import op

revision = "0007_auto_resolve_undo"
down_revision = "0006_device_and_scheduler"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exceptions",
        sa.Column("auto_resolve_undone_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "exceptions", sa.Column("auto_resolve_undone_by", sa.String(length=8), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("exceptions", "auto_resolve_undone_by")
    op.drop_column("exceptions", "auto_resolve_undone_at")
