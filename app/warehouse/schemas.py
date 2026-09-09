from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.orders.models import OrderStatus
from app.warehouse.models import PickTaskStatus


class PickTaskLineResponse(BaseModel):
    order_line_id: str
    sku: str
    quantity_to_pick: int
    picked_quantity: int
    short_quantity: int


class PickTaskResponse(BaseModel):
    pick_task_id: str
    order_id: str
    warehouse_id: str
    status: PickTaskStatus
    lines: list[PickTaskLineResponse]
    correlation_id: str
    created_at: datetime
    completed_at: datetime | None


class PickTaskLineComplete(BaseModel):
    order_line_id: str = Field(min_length=1, examples=["order-line-id-from-pick-task"])
    picked_quantity: int = Field(ge=0, examples=[2])


class CompletePickTaskRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "lines": [
                        {
                            "order_line_id": "order-line-id-from-pick-task",
                            "picked_quantity": 2,
                        }
                    ]
                }
            ]
        }
    )

    lines: list[PickTaskLineComplete] = Field(min_length=1)


class CompletePickTaskResponse(BaseModel):
    pick_task: PickTaskResponse
    order_id: str
    order_status: OrderStatus
