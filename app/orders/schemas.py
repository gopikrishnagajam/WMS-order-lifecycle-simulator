from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.orders.models import OrderStatus


class OrderLineCreate(BaseModel):
    sku: str = Field(min_length=1, examples=["SKU-RED-SHIRT"])
    quantity: int = Field(gt=0, examples=[2])


class OrderCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "external_order_id": "OMS-1001",
                    "warehouse_id": "WH-01",
                    "customer_id": "CUST-01",
                    "lines": [
                        {
                            "sku": "SKU-RED-SHIRT",
                            "quantity": 2,
                        }
                    ],
                }
            ]
        }
    )

    external_order_id: str = Field(min_length=1, examples=["OMS-1001"])
    warehouse_id: str = Field(min_length=1, examples=["WH-01"])
    customer_id: str | None = Field(default=None, examples=["CUST-01"])
    lines: list[OrderLineCreate] = Field(min_length=1)


class OrderLineResponse(BaseModel):
    line_id: str
    sku: str
    quantity: int
    allocated_quantity: int
    picked_quantity: int
    cancelled_quantity: int


class ResolveShortPickRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: Literal["CANCEL_REMAINDER"] = Field(examples=["CANCEL_REMAINDER"])


class OrderResponse(BaseModel):
    order_id: str
    external_order_id: str
    warehouse_id: str
    customer_id: str | None
    status: OrderStatus
    lines: list[OrderLineResponse]
    pick_task_id: str | None
    shipment_id: str | None
    correlation_id: str
    idempotency_key: str
    idempotency_replayed: bool
    created_at: datetime
