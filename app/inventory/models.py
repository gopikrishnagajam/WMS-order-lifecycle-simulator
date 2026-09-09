from dataclasses import dataclass


@dataclass(frozen=True)
class InventoryAllocationRequest:
    sku: str
    quantity: int


@dataclass(frozen=True)
class InventoryAllocation:
    sku: str
    warehouse_id: str
    quantity: int


@dataclass
class InventoryItem:
    sku: str
    warehouse_id: str
    description: str
    on_hand_quantity: int
    allocated_quantity: int = 0

    @property
    def available_quantity(self) -> int:
        return self.on_hand_quantity - self.allocated_quantity

