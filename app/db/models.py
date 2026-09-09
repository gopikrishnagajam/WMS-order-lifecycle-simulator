from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DbOrder(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_order_id: Mapped[str] = mapped_column(String(100), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    pick_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    shipment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
    )
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    lines: Mapped[list[DbOrderLine]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="DbOrderLine.line_id",
    )


class DbOrderLine(Base):
    __tablename__ = "order_lines"

    line_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    picked_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    cancelled_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    order: Mapped[DbOrder] = relationship(back_populates="lines")


class DbInventoryItem(Base):
    __tablename__ = "inventory_items"

    sku: Mapped[str] = mapped_column(String(100), primary_key=True)
    warehouse_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    on_hand_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class DbPickTask(Base):
    __tablename__ = "pick_tasks"

    pick_task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    lines: Mapped[list[DbPickTaskLine]] = relationship(
        back_populates="pick_task",
        cascade="all, delete-orphan",
        order_by="DbPickTaskLine.order_line_id",
    )


class DbPickTaskLine(Base):
    __tablename__ = "pick_task_lines"

    pick_task_id: Mapped[str] = mapped_column(
        ForeignKey("pick_tasks.pick_task_id"),
        primary_key=True,
    )
    order_line_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity_to_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    picked_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    pick_task: Mapped[DbPickTask] = relationship(back_populates="lines")


class DbShipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (UniqueConstraint("order_id", name="uq_shipments_order_id"),)

    shipment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    packed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    shipped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    carrier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    lines: Mapped[list[DbShipmentLine]] = relationship(
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="DbShipmentLine.order_line_id",
    )


class DbShipmentLine(Base):
    __tablename__ = "shipment_lines"

    shipment_id: Mapped[str] = mapped_column(
        ForeignKey("shipments.shipment_id"),
        primary_key=True,
    )
    order_line_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    shipment: Mapped[DbShipment] = relationship(back_populates="lines")


class DbIntegrationMessage(Base):
    __tablename__ = "integration_messages"

    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DbDeadLetterMessage(Base):
    __tablename__ = "dead_letter_messages"

    dead_letter_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_message_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    final_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
