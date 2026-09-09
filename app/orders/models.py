from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class OrderStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    ALLOCATED = "ALLOCATED"
    PICKING = "PICKING"
    PICKED = "PICKED"
    SHORT_PICK = "SHORT_PICK"
    SHORT_PICK_RESOLVED = "SHORT_PICK_RESOLVED"
    CANCELLED = "CANCELLED"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    CONFIRMATION_PUBLISHED = "CONFIRMATION_PUBLISHED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class OrderLine:
    line_id: str
    sku: str
    quantity: int
    allocated_quantity: int
    picked_quantity: int
    cancelled_quantity: int = 0


@dataclass(frozen=True)
class Order:
    order_id: str
    external_order_id: str
    warehouse_id: str
    customer_id: str | None
    status: OrderStatus
    lines: tuple[OrderLine, ...]
    pick_task_id: str | None
    shipment_id: str | None
    correlation_id: str
    idempotency_key: str
    request_fingerprint: str
    created_at: datetime
