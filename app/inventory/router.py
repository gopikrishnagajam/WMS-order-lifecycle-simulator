from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.inventory.dependencies import get_inventory_repository
from app.inventory.models import InventoryItem
from app.inventory.repository import InventoryRepository
from app.inventory.schemas import InventoryItemResponse

router = APIRouter(tags=["inventory"])


@router.get("/inventory", response_model=list[InventoryItemResponse])
def list_inventory(
    repository: Annotated[
        InventoryRepository,
        Depends(get_inventory_repository),
    ],
    warehouse_id: Annotated[str | None, Query(min_length=1)] = None,
) -> list[InventoryItemResponse]:
    return [
        _inventory_item_to_response(item)
        for item in repository.list_items(warehouse_id)
    ]


def _inventory_item_to_response(item: InventoryItem) -> InventoryItemResponse:
    return InventoryItemResponse(
        sku=item.sku,
        warehouse_id=item.warehouse_id,
        description=item.description,
        on_hand_quantity=item.on_hand_quantity,
        allocated_quantity=item.allocated_quantity,
        available_quantity=item.available_quantity,
    )
