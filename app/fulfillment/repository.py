from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import DbShipment, DbShipmentLine
from app.fulfillment.models import Shipment, ShipmentLine, ShipmentStatus
from app.orders.models import Order


class ShipmentAlreadyExistsError(Exception):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"Shipment already exists for order: {order_id}")


class ShipmentNotFoundError(Exception):
    def __init__(self, shipment_id: str) -> None:
        self.shipment_id = shipment_id
        super().__init__(f"Shipment not found: {shipment_id}")


class ShipmentNotFoundForOrderError(Exception):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"Shipment not found for order: {order_id}")


class ShipmentAlreadyShippedError(Exception):
    def __init__(self, shipment_id: str) -> None:
        self.shipment_id = shipment_id
        super().__init__(f"Shipment already shipped: {shipment_id}")


class ShipmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_for_order(self, order: Order) -> Shipment:
        if self.get_by_order_id(order.order_id) is not None:
            raise ShipmentAlreadyExistsError(order.order_id)

        db_shipment = DbShipment(
            shipment_id=str(uuid4()),
            order_id=order.order_id,
            warehouse_id=order.warehouse_id,
            status=ShipmentStatus.PACKED,
            correlation_id=order.correlation_id,
            packed_at=datetime.now(UTC),
            shipped_at=None,
            carrier=None,
            tracking_number=None,
            lines=[
                DbShipmentLine(
                    order_line_id=line.line_id,
                    sku=line.sku,
                    quantity=line.picked_quantity,
                )
                for line in order.lines
                if line.picked_quantity > 0
            ],
        )
        self._session.add(db_shipment)
        self._session.flush()

        return _shipment_to_domain(db_shipment)

    def get(self, shipment_id: str) -> Shipment | None:
        db_shipment = self._get_db_shipment(shipment_id)
        if db_shipment is None:
            return None

        return _shipment_to_domain(db_shipment)

    def get_by_order_id(self, order_id: str) -> Shipment | None:
        db_shipment = self._session.scalar(
            select(DbShipment)
            .options(selectinload(DbShipment.lines))
            .where(DbShipment.order_id == order_id)
        )
        if db_shipment is None:
            return None

        return _shipment_to_domain(db_shipment)

    def list_shipments(self, order_id: str | None = None) -> list[Shipment]:
        statement = (
            select(DbShipment)
            .options(selectinload(DbShipment.lines))
            .order_by(DbShipment.packed_at)
        )
        if order_id is not None:
            statement = statement.where(DbShipment.order_id == order_id)

        return [
            _shipment_to_domain(shipment)
            for shipment in self._session.scalars(statement).all()
        ]

    def mark_shipped(
        self,
        shipment_id: str,
        carrier: str,
        tracking_number: str,
    ) -> Shipment:
        db_shipment = self._get_db_shipment(shipment_id)
        if db_shipment is None:
            raise ShipmentNotFoundError(shipment_id)

        if db_shipment.status == ShipmentStatus.SHIPPED:
            raise ShipmentAlreadyShippedError(shipment_id)

        db_shipment.status = ShipmentStatus.SHIPPED
        db_shipment.shipped_at = datetime.now(UTC)
        db_shipment.carrier = carrier
        db_shipment.tracking_number = tracking_number
        self._session.flush()

        return _shipment_to_domain(db_shipment)

    def _get_db_shipment(self, shipment_id: str) -> DbShipment | None:
        return self._session.scalar(
            select(DbShipment)
            .options(selectinload(DbShipment.lines))
            .where(DbShipment.shipment_id == shipment_id)
        )


def _shipment_to_domain(db_shipment: DbShipment) -> Shipment:
    return Shipment(
        shipment_id=db_shipment.shipment_id,
        order_id=db_shipment.order_id,
        warehouse_id=db_shipment.warehouse_id,
        status=ShipmentStatus(db_shipment.status),
        lines=tuple(
            ShipmentLine(
                order_line_id=line.order_line_id,
                sku=line.sku,
                quantity=line.quantity,
            )
            for line in db_shipment.lines
        ),
        correlation_id=db_shipment.correlation_id,
        packed_at=db_shipment.packed_at,
        shipped_at=db_shipment.shipped_at,
        carrier=db_shipment.carrier,
        tracking_number=db_shipment.tracking_number,
    )


InMemoryShipmentRepository = ShipmentRepository
