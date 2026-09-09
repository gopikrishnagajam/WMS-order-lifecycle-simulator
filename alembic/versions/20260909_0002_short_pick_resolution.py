"""Preserve cancelled quantities when resolving short picks."""

from alembic import op
import sqlalchemy as sa

revision = "20260909_0002"
down_revision = "20260908_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_lines",
        sa.Column("cancelled_quantity", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("order_lines", "cancelled_quantity")
