from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ShipmentStatus(StrEnum):
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"


@dataclass(frozen=True)
class ShipmentLine:
    order_line_id: str
    sku: str
    quantity: int


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    order_id: str
    warehouse_id: str
    status: ShipmentStatus
    lines: tuple[ShipmentLine, ...]
    correlation_id: str
    packed_at: datetime
    shipped_at: datetime | None
    carrier: str | None
    tracking_number: str | None

