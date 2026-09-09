from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DbInventoryItem
from app.inventory.models import (
    InventoryAllocation,
    InventoryAllocationRequest,
    InventoryItem,
)


class UnknownWarehouseError(Exception):
    def __init__(self, warehouse_id: str) -> None:
        self.warehouse_id = warehouse_id
        super().__init__(f"Unknown warehouse: {warehouse_id}")


class UnknownSkuError(Exception):
    def __init__(self, sku: str) -> None:
        self.sku = sku
        super().__init__(f"Unknown SKU: {sku}")


class InventoryNotStockedError(Exception):
    def __init__(self, sku: str, warehouse_id: str) -> None:
        self.sku = sku
        self.warehouse_id = warehouse_id
        super().__init__(f"SKU {sku} is not stocked at warehouse {warehouse_id}")


class InsufficientInventoryError(Exception):
    def __init__(
        self,
        sku: str,
        warehouse_id: str,
        requested_quantity: int,
        available_quantity: int,
    ) -> None:
        self.sku = sku
        self.warehouse_id = warehouse_id
        self.requested_quantity = requested_quantity
        self.available_quantity = available_quantity
        super().__init__(
            f"Insufficient inventory for {sku} at {warehouse_id}: "
            f"requested {requested_quantity}, available {available_quantity}"
        )


class InventoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_items(self, warehouse_id: str | None = None) -> list[InventoryItem]:
        statement = select(DbInventoryItem).order_by(
            DbInventoryItem.warehouse_id,
            DbInventoryItem.sku,
        )
        if warehouse_id is not None:
            statement = statement.where(DbInventoryItem.warehouse_id == warehouse_id)

        return [
            _inventory_item_to_domain(item)
            for item in self._session.scalars(statement).all()
        ]

    def allocate(
        self,
        warehouse_id: str,
        requests: Iterable[InventoryAllocationRequest],
    ) -> list[InventoryAllocation]:
        required_quantities: dict[str, int] = {}
        for request in requests:
            required_quantities[request.sku] = (
                required_quantities.get(request.sku, 0) + request.quantity
            )

        if not self._warehouse_exists(warehouse_id):
            raise UnknownWarehouseError(warehouse_id)

        db_items_by_sku: dict[str, DbInventoryItem] = {}
        for sku, requested_quantity in sorted(required_quantities.items()):
            if not self._sku_exists(sku):
                raise UnknownSkuError(sku)

            db_item = self._get_inventory_item(warehouse_id=warehouse_id, sku=sku)
            if db_item is None:
                raise InventoryNotStockedError(sku=sku, warehouse_id=warehouse_id)

            available_quantity = db_item.on_hand_quantity - db_item.allocated_quantity
            if available_quantity < requested_quantity:
                raise InsufficientInventoryError(
                    sku=sku,
                    warehouse_id=warehouse_id,
                    requested_quantity=requested_quantity,
                    available_quantity=available_quantity,
                )

            db_items_by_sku[sku] = db_item

        allocations: list[InventoryAllocation] = []
        for sku, requested_quantity in required_quantities.items():
            db_item = db_items_by_sku[sku]
            db_item.allocated_quantity += requested_quantity
            allocations.append(
                InventoryAllocation(
                    sku=sku,
                    warehouse_id=warehouse_id,
                    quantity=requested_quantity,
                )
            )

        self._session.flush()
        return allocations

    def release_or_ship(
        self,
        warehouse_id: str,
        quantities: dict[str, int],
        *,
        shipped: bool = False,
    ) -> None:
        """Release cancelled reservations or consume stock at shipment time."""
        for sku, quantity in sorted(quantities.items()):
            if quantity < 0:
                raise ValueError("Inventory movement cannot be negative.")
            if quantity == 0:
                continue
            item = self._get_inventory_item(warehouse_id, sku)
            if item is None or item.allocated_quantity < quantity:
                raise ValueError("Inventory reservation is inconsistent with the order.")
            if shipped and item.on_hand_quantity < quantity:
                raise ValueError("On-hand inventory is insufficient for shipment.")
            item.allocated_quantity -= quantity
            if shipped:
                item.on_hand_quantity -= quantity
        self._session.flush()

    def _warehouse_exists(self, warehouse_id: str) -> bool:
        return (
            self._session.scalar(
                select(DbInventoryItem.warehouse_id)
                .where(DbInventoryItem.warehouse_id == warehouse_id)
                .limit(1)
            )
            is not None
        )

    def _sku_exists(self, sku: str) -> bool:
        return (
            self._session.scalar(
                select(DbInventoryItem.sku)
                .where(DbInventoryItem.sku == sku)
                .limit(1)
            )
            is not None
        )

    def _get_inventory_item(
        self,
        warehouse_id: str,
        sku: str,
    ) -> DbInventoryItem | None:
        return self._session.scalar(
            select(DbInventoryItem).where(
                DbInventoryItem.warehouse_id == warehouse_id,
                DbInventoryItem.sku == sku,
            ).with_for_update().execution_options(populate_existing=True)
        )


def _inventory_item_to_domain(item: DbInventoryItem) -> InventoryItem:
    return InventoryItem(
        sku=item.sku,
        warehouse_id=item.warehouse_id,
        description=item.description,
        on_hand_quantity=item.on_hand_quantity,
        allocated_quantity=item.allocated_quantity,
    )


InMemoryInventoryRepository = InventoryRepository
