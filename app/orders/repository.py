import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import DbOrder, DbOrderLine
from app.orders.models import Order, OrderLine, OrderStatus
from app.orders.schemas import OrderCreate, OrderLineResponse, OrderResponse


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with a different request body."""


@dataclass(frozen=True)
class CreateOrderResult:
    order: Order
    replayed: bool


class OrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_idempotent_order(
        self,
        order_request: OrderCreate,
        idempotency_key: str,
    ) -> CreateOrderResult | None:
        request_fingerprint = _fingerprint_order_request(order_request)
        existing_order = self._get_by_idempotency_key(idempotency_key)
        if existing_order is None:
            return None

        if existing_order.request_fingerprint != request_fingerprint:
            raise IdempotencyConflictError

        return CreateOrderResult(order=_order_to_domain(existing_order), replayed=True)

    def create_new(
        self,
        order_request: OrderCreate,
        idempotency_key: str,
        correlation_id: str,
        status: OrderStatus,
    ) -> Order:
        request_fingerprint = _fingerprint_order_request(order_request)
        if self._get_by_idempotency_key(idempotency_key) is not None:
            raise IdempotencyConflictError

        order = _create_order(
            order_request=order_request,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_fingerprint=request_fingerprint,
            status=status,
        )
        db_order = _domain_order_to_db(order)
        self._session.add(db_order)

        try:
            self._session.flush()
        except IntegrityError as exc:
            raise IdempotencyConflictError from exc

        return _order_to_domain(db_order)

    def get(self, order_id: str) -> Order | None:
        db_order = self._get_db_order(order_id)
        if db_order is None:
            return None

        return _order_to_domain(db_order)

    def list_orders(self) -> list[Order]:
        db_orders = self._session.scalars(
            select(DbOrder)
            .options(selectinload(DbOrder.lines))
            .order_by(DbOrder.created_at.desc())
        ).all()
        return [_order_to_domain(order) for order in db_orders]

    def get_for_update(self, order_id: str) -> Order | None:
        db_order = self._session.scalar(
            select(DbOrder)
            .options(selectinload(DbOrder.lines))
            .where(DbOrder.order_id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return _order_to_domain(db_order) if db_order is not None else None

    def cancel_unpicked_remainder(self, order_id: str) -> Order:
        db_order = self._get_db_order(order_id)
        if db_order is None:
            raise ValueError("Order disappeared during short-pick resolution.")
        for line in db_order.lines:
            line.cancelled_quantity = line.quantity - line.picked_quantity
            line.allocated_quantity = line.picked_quantity
        db_order.status = (
            OrderStatus.SHORT_PICK_RESOLVED
            if any(line.picked_quantity for line in db_order.lines)
            else OrderStatus.CANCELLED
        )
        self._session.flush()
        return _order_to_domain(db_order)

    def assign_pick_task(self, order_id: str, pick_task_id: str) -> Order | None:
        db_order = self._get_db_order(order_id)
        if db_order is None:
            return None

        db_order.status = OrderStatus.PICKING
        db_order.pick_task_id = pick_task_id
        self._session.flush()

        return _order_to_domain(db_order)

    def assign_shipment(
        self,
        order_id: str,
        shipment_id: str,
        status: OrderStatus,
    ) -> Order | None:
        db_order = self._get_db_order(order_id)
        if db_order is None:
            return None

        db_order.status = status
        db_order.shipment_id = shipment_id
        self._session.flush()

        return _order_to_domain(db_order)

    def update_status(self, order_id: str, status: OrderStatus) -> Order | None:
        db_order = self._get_db_order(order_id)
        if db_order is None:
            return None

        db_order.status = status
        self._session.flush()

        return _order_to_domain(db_order)

    def record_pick_result(
        self,
        order_id: str,
        picked_quantities_by_order_line_id: dict[str, int],
        status: OrderStatus,
    ) -> Order | None:
        db_order = self._get_db_order(order_id)
        if db_order is None:
            return None

        db_order.status = status
        for line in db_order.lines:
            line.picked_quantity = picked_quantities_by_order_line_id[line.line_id]
        self._session.flush()

        return _order_to_domain(db_order)

    def _get_db_order(self, order_id: str) -> DbOrder | None:
        return self._session.scalar(
            select(DbOrder)
            .options(selectinload(DbOrder.lines))
            .where(DbOrder.order_id == order_id)
        )

    def _get_by_idempotency_key(self, idempotency_key: str) -> DbOrder | None:
        return self._session.scalar(
            select(DbOrder)
            .options(selectinload(DbOrder.lines))
            .where(DbOrder.idempotency_key == idempotency_key)
        )


def order_to_response(order: Order, replayed: bool = False) -> OrderResponse:
    return OrderResponse(
        order_id=order.order_id,
        external_order_id=order.external_order_id,
        warehouse_id=order.warehouse_id,
        customer_id=order.customer_id,
        status=order.status,
        lines=[
            OrderLineResponse(
                line_id=line.line_id,
                sku=line.sku,
                quantity=line.quantity,
                allocated_quantity=line.allocated_quantity,
                picked_quantity=line.picked_quantity,
                cancelled_quantity=line.cancelled_quantity,
            )
            for line in order.lines
        ],
        pick_task_id=order.pick_task_id,
        shipment_id=order.shipment_id,
        correlation_id=order.correlation_id,
        idempotency_key=order.idempotency_key,
        idempotency_replayed=replayed,
        created_at=order.created_at,
    )


def _fingerprint_order_request(order_request: OrderCreate) -> str:
    payload = order_request.model_dump(mode="json")
    serialized_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()


def _create_order(
    order_request: OrderCreate,
    idempotency_key: str,
    correlation_id: str,
    request_fingerprint: str,
    status: OrderStatus,
) -> Order:
    return Order(
        order_id=str(uuid4()),
        external_order_id=order_request.external_order_id,
        warehouse_id=order_request.warehouse_id,
        customer_id=order_request.customer_id,
        status=status,
        lines=tuple(
            OrderLine(
                line_id=str(uuid4()),
                sku=line.sku,
                quantity=line.quantity,
                allocated_quantity=(
                    line.quantity if status == OrderStatus.ALLOCATED else 0
                ),
                picked_quantity=0,
            )
            for line in order_request.lines
        ),
        pick_task_id=None,
        shipment_id=None,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        created_at=datetime.now(UTC),
    )


def _domain_order_to_db(order: Order) -> DbOrder:
    return DbOrder(
        order_id=order.order_id,
        external_order_id=order.external_order_id,
        warehouse_id=order.warehouse_id,
        customer_id=order.customer_id,
        status=order.status,
        pick_task_id=order.pick_task_id,
        shipment_id=order.shipment_id,
        correlation_id=order.correlation_id,
        idempotency_key=order.idempotency_key,
        request_fingerprint=order.request_fingerprint,
        created_at=order.created_at,
        lines=[
            DbOrderLine(
                line_id=line.line_id,
                sku=line.sku,
                quantity=line.quantity,
                allocated_quantity=line.allocated_quantity,
                picked_quantity=line.picked_quantity,
                cancelled_quantity=line.cancelled_quantity,
            )
            for line in order.lines
        ],
    )


def _order_to_domain(db_order: DbOrder) -> Order:
    return Order(
        order_id=db_order.order_id,
        external_order_id=db_order.external_order_id,
        warehouse_id=db_order.warehouse_id,
        customer_id=db_order.customer_id,
        status=OrderStatus(db_order.status),
        lines=tuple(
            OrderLine(
                line_id=line.line_id,
                sku=line.sku,
                quantity=line.quantity,
                allocated_quantity=line.allocated_quantity,
                picked_quantity=line.picked_quantity,
                cancelled_quantity=line.cancelled_quantity,
            )
            for line in db_order.lines
        ),
        pick_task_id=db_order.pick_task_id,
        shipment_id=db_order.shipment_id,
        correlation_id=db_order.correlation_id,
        idempotency_key=db_order.idempotency_key,
        request_fingerprint=db_order.request_fingerprint,
        created_at=db_order.created_at,
    )


InMemoryOrderRepository = OrderRepository
