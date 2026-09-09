import logging
from threading import Lock

from app.core.logging import log_event
from app.inventory.models import InventoryAllocationRequest
from app.inventory.repository import InventoryRepository
from app.orders.models import Order, OrderStatus
from app.orders.repository import (
    CreateOrderResult,
    OrderRepository,
)
from app.orders.schemas import OrderCreate
from app.warehouse.repository import PickTaskRepository

logger = logging.getLogger(__name__)


class ShortPickOrderNotFoundError(Exception):
    pass


class OrderCannotResolveShortPickError(Exception):
    pass


class OrderService:
    def __init__(
        self,
        order_repository: OrderRepository,
        inventory_repository: InventoryRepository,
        pick_task_repository: PickTaskRepository,
    ) -> None:
        self._order_repository = order_repository
        self._inventory_repository = inventory_repository
        self._pick_task_repository = pick_task_repository
        self._lock = Lock()

    def create_order(
        self,
        order_request: OrderCreate,
        idempotency_key: str,
        correlation_id: str,
    ) -> CreateOrderResult:
        with self._lock:
            existing_order = self._order_repository.find_idempotent_order(
                order_request=order_request,
                idempotency_key=idempotency_key,
            )
            if existing_order is not None:
                log_event(
                    logger,
                    "order_idempotency_replayed",
                    order_id=existing_order.order.order_id,
                    idempotency_key=idempotency_key,
                    status=existing_order.order.status,
                )
                return existing_order

            allocations = self._inventory_repository.allocate(
                warehouse_id=order_request.warehouse_id,
                requests=[
                    InventoryAllocationRequest(
                        sku=line.sku,
                        quantity=line.quantity,
                    )
                    for line in order_request.lines
                ],
            )
            log_event(
                logger,
                "inventory_allocated",
                external_order_id=order_request.external_order_id,
                warehouse_id=order_request.warehouse_id,
                allocated_lines=len(allocations),
            )

            order = self._order_repository.create_new(
                order_request=order_request,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                status=OrderStatus.ALLOCATED,
            )
            pick_task = self._pick_task_repository.create_for_order(order)
            picking_order = self._order_repository.assign_pick_task(
                order_id=order.order_id,
                pick_task_id=pick_task.pick_task_id,
            )
            if picking_order is None:
                return CreateOrderResult(order=order, replayed=False)

            log_event(
                logger,
                "order_created",
                order_id=picking_order.order_id,
                external_order_id=picking_order.external_order_id,
                status=picking_order.status,
                pick_task_id=picking_order.pick_task_id,
            )

            return CreateOrderResult(order=picking_order, replayed=False)

    def get_order(self, order_id: str) -> Order | None:
        return self._order_repository.get(order_id)

    def list_orders(self) -> list[Order]:
        return self._order_repository.list_orders()

    def resolve_short_pick(self, order_id: str) -> Order:
        order = self._order_repository.get_for_update(order_id)
        if order is None:
            raise ShortPickOrderNotFoundError
        # Persisted cancellations make repeat calls safe even after shipping.
        if any(line.cancelled_quantity for line in order.lines):
            return order
        if order.status != OrderStatus.SHORT_PICK:
            raise OrderCannotResolveShortPickError(
                f"Only SHORT_PICK orders can be resolved. Current status: {order.status}."
            )
        releases: dict[str, int] = {}
        for line in order.lines:
            releases[line.sku] = releases.get(line.sku, 0) + (
                line.allocated_quantity - line.picked_quantity
            )
        self._inventory_repository.release_or_ship(order.warehouse_id, releases)
        resolved = self._order_repository.cancel_unpicked_remainder(order_id)
        log_event(
            logger,
            "short_pick_resolved",
            order_id=order_id,
            policy="CANCEL_REMAINDER",
            cancelled_quantity=sum(releases.values()),
            status=resolved.status,
        )
        return resolved
