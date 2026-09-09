from pydantic import BaseModel


class InventoryItemResponse(BaseModel):
    sku: str
    warehouse_id: str
    description: str
    on_hand_quantity: int
    allocated_quantity: int
    available_quantity: int

