import logging
from uuid import uuid4

from app.core.logging import log_event
from app.fulfillment.models import Shipment
from app.fulfillment.repository import (
    ShipmentRepository,
    ShipmentAlreadyExistsError,
    ShipmentNotFoundForOrderError,
)
from app.fulfillment.schemas import ShipOrderRequest
from app.integration.models import IntegrationMessage
from app.integration.repository import IntegrationMessageRepository
from app.orders.models import Order, OrderStatus
from app.orders.repository import OrderRepository
from app.inventory.repository import InventoryRepository

logger = logging.getLogger(__name__)


class OrderNotFoundError(Exception):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"Order not found: {order_id}")


class OrderCannotBePackedError(Exception):
    def __init__(self, order_id: str, current_status: OrderStatus) -> None:
        self.order_id = order_id
        self.current_status = current_status
        super().__init__(f"Order {order_id} cannot be packed from {current_status}")


class ShortPickCannotBePackedError(Exception):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"Short-pick order cannot be packed: {order_id}")


class OrderCannotBeShippedError(Exception):
    def __init__(self, order_id: str, current_status: OrderStatus) -> None:
        self.order_id = order_id
        self.current_status = current_status
        super().__init__(f"Order {order_id} cannot be shipped from {current_status}")


class FulfillmentOrderSyncError(Exception):
    pass


class FulfillmentService:
    def __init__(
        self,
        order_repository: OrderRepository,
        shipment_repository: ShipmentRepository,
        integration_message_repository: IntegrationMessageRepository,
        inventory_repository: InventoryRepository,
    ) -> None:
        self._order_repository = order_repository
        self._shipment_repository = shipment_repository
        self._integration_message_repository = integration_message_repository
        self._inventory_repository = inventory_repository

    def list_shipments(self, order_id: str | None = None) -> list[Shipment]:
        return self._shipment_repository.list_shipments(order_id=order_id)

    def get_shipment(self, shipment_id: str) -> Shipment | None:
        return self._shipment_repository.get(shipment_id)

    def pack_order(self, order_id: str) -> tuple[Order, Shipment]:
        order = self._get_order_or_raise(order_id)
        if order.status == OrderStatus.SHORT_PICK:
            raise ShortPickCannotBePackedError(order_id)

        if order.status not in {OrderStatus.PICKED, OrderStatus.SHORT_PICK_RESOLVED}:
            raise OrderCannotBePackedError(
                order_id=order_id,
                current_status=order.status,
            )

        try:
            shipment = self._shipment_repository.create_for_order(order)
        except ShipmentAlreadyExistsError as exc:
            raise OrderCannotBePackedError(
                order_id=order_id,
                current_status=order.status,
            ) from exc

        packed_order = self._order_repository.assign_shipment(
            order_id=order.order_id,
            shipment_id=shipment.shipment_id,
            status=OrderStatus.PACKED,
        )
        if packed_order is None:
            raise FulfillmentOrderSyncError

        log_event(
            logger,
            "order_packed",
            order_id=packed_order.order_id,
            shipment_id=shipment.shipment_id,
            order_status=packed_order.status,
            shipment_status=shipment.status,
        )

        return packed_order, shipment

    def ship_order(
        self,
        order_id: str,
        request: ShipOrderRequest,
    ) -> tuple[Order, Shipment, IntegrationMessage]:
        order = self._get_order_or_raise(order_id)
        if order.status != OrderStatus.PACKED:
            raise OrderCannotBeShippedError(
                order_id=order_id,
                current_status=order.status,
            )

        shipment = self._shipment_repository.get_by_order_id(order_id)
        if shipment is None:
            raise ShipmentNotFoundForOrderError(order_id)

        quantities: dict[str, int] = {}
        for line in shipment.lines:
            quantities[line.sku] = quantities.get(line.sku, 0) + line.quantity
        self._inventory_repository.release_or_ship(
            order.warehouse_id, quantities, shipped=True
        )

        shipped_shipment = self._shipment_repository.mark_shipped(
            shipment_id=shipment.shipment_id,
            carrier=request.carrier,
            tracking_number=request.tracking_number or _generate_tracking_number(),
        )
        shipped_order = self._order_repository.update_status(
            order_id=order_id,
            status=OrderStatus.SHIPPED,
        )
        if shipped_order is None:
            raise FulfillmentOrderSyncError

        message = self._integration_message_repository.create_shipment_confirmation(
            order=shipped_order,
            shipment=shipped_shipment,
        )

        log_event(
            logger,
            "order_shipped",
            order_id=shipped_order.order_id,
            shipment_id=shipped_shipment.shipment_id,
            message_id=message.message_id,
            order_status=shipped_order.status,
            shipment_status=shipped_shipment.status,
            message_status=message.status,
        )

        return shipped_order, shipped_shipment, message

    def _get_order_or_raise(self, order_id: str) -> Order:
        order = self._order_repository.get_for_update(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)

        return order


def _generate_tracking_number() -> str:
    return f"TRK-{uuid4().hex[:12].upper()}"
