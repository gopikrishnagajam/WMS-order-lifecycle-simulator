"""Initial WMS simulator schema.

Revision ID: 20260908_0001
Revises:
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_items",
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("warehouse_id", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("on_hand_quantity", sa.Integer(), nullable=False),
        sa.Column("allocated_quantity", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("sku", "warehouse_id"),
    )
    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("external_order_id", sa.String(length=100), nullable=False),
        sa.Column("warehouse_id", sa.String(length=50), nullable=False),
        sa.Column("customer_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("pick_task_id", sa.String(length=36), nullable=True),
        sa.Column("shipment_id", sa.String(length=36), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("order_id"),
    )
    op.create_index(op.f("ix_orders_idempotency_key"), "orders", ["idempotency_key"], unique=True)
    op.create_table(
        "order_lines",
        sa.Column("line_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("allocated_quantity", sa.Integer(), nullable=False),
        sa.Column("picked_quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.order_id"]),
        sa.PrimaryKeyConstraint("line_id"),
    )
    op.create_index(op.f("ix_order_lines_order_id"), "order_lines", ["order_id"], unique=False)
    op.create_table(
        "pick_tasks",
        sa.Column("pick_task_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("warehouse_id", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.order_id"]),
        sa.PrimaryKeyConstraint("pick_task_id"),
    )
    op.create_index(op.f("ix_pick_tasks_order_id"), "pick_tasks", ["order_id"], unique=False)
    op.create_table(
        "pick_task_lines",
        sa.Column("pick_task_id", sa.String(length=36), nullable=False),
        sa.Column("order_line_id", sa.String(length=36), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("quantity_to_pick", sa.Integer(), nullable=False),
        sa.Column("picked_quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["pick_task_id"], ["pick_tasks.pick_task_id"]),
        sa.PrimaryKeyConstraint("pick_task_id", "order_line_id"),
    )
    op.create_table(
        "shipments",
        sa.Column("shipment_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("warehouse_id", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column("packed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("carrier", sa.String(length=100), nullable=True),
        sa.Column("tracking_number", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.order_id"]),
        sa.PrimaryKeyConstraint("shipment_id"),
        sa.UniqueConstraint("order_id", name="uq_shipments_order_id"),
    )
    op.create_index(op.f("ix_shipments_order_id"), "shipments", ["order_id"], unique=False)
    op.create_table(
        "shipment_lines",
        sa.Column("shipment_id", sa.String(length=36), nullable=False),
        sa.Column("order_line_id", sa.String(length=36), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.shipment_id"]),
        sa.PrimaryKeyConstraint("shipment_id", "order_line_id"),
    )
    op.create_table(
        "integration_messages",
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_table(
        "dead_letter_messages",
        sa.Column("dead_letter_id", sa.String(length=36), nullable=False),
        sa.Column("original_message_id", sa.String(length=36), nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("final_attempt_count", sa.Integer(), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dead_letter_id"),
    )
    op.create_index(
        op.f("ix_dead_letter_messages_original_message_id"),
        "dead_letter_messages",
        ["original_message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dead_letter_messages_original_message_id"), table_name="dead_letter_messages")
    op.drop_table("dead_letter_messages")
    op.drop_table("integration_messages")
    op.drop_table("shipment_lines")
    op.drop_index(op.f("ix_shipments_order_id"), table_name="shipments")
    op.drop_table("shipments")
    op.drop_table("pick_task_lines")
    op.drop_index(op.f("ix_pick_tasks_order_id"), table_name="pick_tasks")
    op.drop_table("pick_tasks")
    op.drop_index(op.f("ix_order_lines_order_id"), table_name="order_lines")
    op.drop_table("order_lines")
    op.drop_index(op.f("ix_orders_idempotency_key"), table_name="orders")
    op.drop_table("orders")
    op.drop_table("inventory_items")

