from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class PickTaskStatus(StrEnum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    SHORT_PICK = "SHORT_PICK"


@dataclass(frozen=True)
class PickTaskLine:
    order_line_id: str
    sku: str
    quantity_to_pick: int
    picked_quantity: int

    @property
    def short_quantity(self) -> int:
        return self.quantity_to_pick - self.picked_quantity


@dataclass(frozen=True)
class PickTask:
    pick_task_id: str
    order_id: str
    warehouse_id: str
    status: PickTaskStatus
    lines: tuple[PickTaskLine, ...]
    correlation_id: str
    created_at: datetime
    completed_at: datetime | None

