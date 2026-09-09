import logging
from threading import Lock

from app.core.logging import log_event
from app.orders.models import Order, OrderStatus
from app.orders.repository import OrderRepository
from app.warehouse.models import PickTask
from app.warehouse.models import PickTaskStatus
from app.warehouse.repository import (
    DuplicatePickLineError,
    PickTaskRepository,
)
from app.warehouse.schemas import CompletePickTaskRequest

logger = logging.getLogger(__name__)


class WarehouseOrderSyncError(Exception):
    pass


class WarehouseService:
    def __init__(
        self,
        pick_task_repository: PickTaskRepository,
        order_repository: OrderRepository,
    ) -> None:
        self._pick_task_repository = pick_task_repository
        self._order_repository = order_repository
        self._lock = Lock()

    def list_pick_tasks(self, order_id: str | None = None) -> list[PickTask]:
        return self._pick_task_repository.list_tasks(order_id=order_id)

    def get_pick_task(self, pick_task_id: str) -> PickTask | None:
        return self._pick_task_repository.get(pick_task_id)

    def complete_pick_task(
        self,
        pick_task_id: str,
        request: CompletePickTaskRequest,
    ) -> tuple[PickTask, Order]:
        with self._lock:
            picked_quantities = _picked_quantities_by_order_line_id(request)
            pick_task = self._pick_task_repository.complete(
                pick_task_id=pick_task_id,
                picked_quantities_by_order_line_id=picked_quantities,
            )

            order_status = OrderStatus.PICKED
            if pick_task.status == PickTaskStatus.SHORT_PICK:
                order_status = OrderStatus.SHORT_PICK

            order = self._order_repository.record_pick_result(
                order_id=pick_task.order_id,
                picked_quantities_by_order_line_id={
                    line.order_line_id: line.picked_quantity
                    for line in pick_task.lines
                },
                status=order_status,
            )
            if order is None:
                raise WarehouseOrderSyncError

            log_event(
                logger,
                "pick_task_completed",
                pick_task_id=pick_task.pick_task_id,
                order_id=order.order_id,
                pick_task_status=pick_task.status,
                order_status=order.status,
            )

            return pick_task, order


def _picked_quantities_by_order_line_id(
    request: CompletePickTaskRequest,
) -> dict[str, int]:
    picked_quantities: dict[str, int] = {}
    for line in request.lines:
        if line.order_line_id in picked_quantities:
            raise DuplicatePickLineError(line.order_line_id)

        picked_quantities[line.order_line_id] = line.picked_quantity

    return picked_quantities
