from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.fulfillment.models import ShipmentStatus
from app.integration.schemas import IntegrationMessageResponse
from app.orders.schemas import OrderResponse


class ShipmentLineResponse(BaseModel):
    order_line_id: str
    sku: str
    quantity: int


class ShipmentResponse(BaseModel):
    shipment_id: str
    order_id: str
    warehouse_id: str
    status: ShipmentStatus
    lines: list[ShipmentLineResponse]
    correlation_id: str
    packed_at: datetime
    shipped_at: datetime | None
    carrier: str | None
    tracking_number: str | None


class PackOrderResponse(BaseModel):
    order: OrderResponse
    shipment: ShipmentResponse


class ShipOrderRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "carrier": "UPS",
                    "tracking_number": "1Z999AA10123456784",
                },
                {
                    "carrier": "SIM_CARRIER",
                },
            ]
        }
    )

    carrier: str = Field(default="SIM_CARRIER", min_length=1, examples=["UPS"])
    tracking_number: str | None = Field(
        default=None,
        min_length=1,
        examples=["1Z999AA10123456784"],
    )


class ShipOrderResponse(BaseModel):
    order: OrderResponse
    shipment: ShipmentResponse
    shipment_confirmation_message: IntegrationMessageResponse
