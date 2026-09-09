"""Reconcile inventory for shipments made before shipment consumption existed."""

from alembic import op
import sqlalchemy as sa

revision = "20260909_0003"
down_revision = "20260909_0002"
branch_labels = None
depends_on = None


def _reconcile(direction: int) -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("""
        SELECT s.warehouse_id, l.sku, SUM(l.quantity) AS quantity
        FROM shipments s JOIN shipment_lines l ON s.shipment_id = l.shipment_id
        WHERE s.status = 'SHIPPED'
        GROUP BY s.warehouse_id, l.sku
    """)).mappings().all()
    for row in rows:
        result = connection.execute(sa.text("""
            UPDATE inventory_items
            SET on_hand_quantity = on_hand_quantity + :movement,
                allocated_quantity = allocated_quantity + :movement
            WHERE warehouse_id = :warehouse_id AND sku = :sku
              AND on_hand_quantity + :movement >= 0
              AND allocated_quantity + :movement >= 0
        """), {
            "warehouse_id": row["warehouse_id"],
            "sku": row["sku"],
            "movement": direction * row["quantity"],
        })
        if result.rowcount != 1:
            raise RuntimeError("Cannot reconcile shipped inventory; inspect stock balances.")


def upgrade() -> None:
    _reconcile(-1)


def downgrade() -> None:
    _reconcile(1)
