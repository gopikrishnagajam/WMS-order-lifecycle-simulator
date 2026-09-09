from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DbDeadLetterMessage, DbIntegrationMessage
from app.fulfillment.models import Shipment
from app.integration.models import (
    DeadLetterMessage,
    IntegrationMessage,
    IntegrationMessageStatus,
    IntegrationMessageType,
)
from app.orders.models import Order


class IntegrationMessageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_shipment_confirmation(
        self,
        order: Order,
        shipment: Shipment,
    ) -> IntegrationMessage:
        db_message = DbIntegrationMessage(
            message_id=str(uuid4()),
            message_type=IntegrationMessageType.SHIPMENT_CONFIRMATION,
            status=IntegrationMessageStatus.PENDING,
            correlation_id=order.correlation_id,
            payload={
                "order_id": order.order_id,
                "external_order_id": order.external_order_id,
                "warehouse_id": order.warehouse_id,
                "shipment_id": shipment.shipment_id,
                "carrier": shipment.carrier,
                "tracking_number": shipment.tracking_number,
                "shipped_at": (
                    shipment.shipped_at.isoformat()
                    if shipment.shipped_at is not None
                    else None
                ),
                "lines": [
                    {
                        "order_line_id": line.order_line_id,
                        "sku": line.sku,
                        "quantity": line.quantity,
                    }
                    for line in shipment.lines
                ],
                "cancelled_lines": [
                    {
                        "order_line_id": line.line_id,
                        "sku": line.sku,
                        "quantity": line.cancelled_quantity,
                    }
                    for line in order.lines
                    if line.cancelled_quantity > 0
                ],
            },
            attempt_count=0,
            max_attempts=3,
            next_retry_at=None,
            last_error=None,
            published_at=None,
            created_at=datetime.now(UTC),
        )
        self._session.add(db_message)
        self._session.flush()

        return _integration_message_to_domain(db_message)

    def list_messages(self) -> list[IntegrationMessage]:
        return [
            _integration_message_to_domain(message)
            for message in self._session.scalars(
                select(DbIntegrationMessage).order_by(DbIntegrationMessage.created_at)
            ).all()
        ]

    def get(self, message_id: str) -> IntegrationMessage | None:
        db_message = self._session.get(DbIntegrationMessage, message_id)
        if db_message is None:
            return None

        return _integration_message_to_domain(db_message)

    def mark_published(self, message_id: str) -> IntegrationMessage | None:
        db_message = self._session.get(DbIntegrationMessage, message_id)
        if db_message is None:
            return None

        db_message.status = IntegrationMessageStatus.PUBLISHED
        db_message.attempt_count += 1
        db_message.next_retry_at = None
        db_message.last_error = None
        db_message.published_at = datetime.now(UTC)
        self._session.flush()

        return _integration_message_to_domain(db_message)

    def schedule_retry(
        self,
        message_id: str,
        error_message: str,
    ) -> IntegrationMessage | None:
        db_message = self._session.get(DbIntegrationMessage, message_id)
        if db_message is None:
            return None

        next_attempt_count = db_message.attempt_count + 1
        db_message.status = IntegrationMessageStatus.RETRY_SCHEDULED
        db_message.attempt_count = next_attempt_count
        db_message.next_retry_at = datetime.now(UTC) + timedelta(
            minutes=5 * next_attempt_count
        )
        db_message.last_error = error_message
        self._session.flush()

        return _integration_message_to_domain(db_message)

    def dead_letter(
        self,
        message_id: str,
        reason: str,
        count_attempt: bool,
    ) -> tuple[IntegrationMessage, DeadLetterMessage] | None:
        db_message = self._session.get(DbIntegrationMessage, message_id)
        if db_message is None:
            return None

        final_attempt_count = db_message.attempt_count
        if count_attempt:
            final_attempt_count += 1

        db_dead_letter = DbDeadLetterMessage(
            dead_letter_id=str(uuid4()),
            original_message_id=db_message.message_id,
            message_type=db_message.message_type,
            correlation_id=db_message.correlation_id,
            payload=dict(db_message.payload),
            reason=reason,
            final_attempt_count=final_attempt_count,
            failed_at=datetime.now(UTC),
        )
        db_message.status = IntegrationMessageStatus.DEAD_LETTERED
        db_message.attempt_count = final_attempt_count
        db_message.next_retry_at = None
        db_message.last_error = reason

        self._session.add(db_dead_letter)
        self._session.flush()

        return (
            _integration_message_to_domain(db_message),
            _dead_letter_message_to_domain(db_dead_letter),
        )

    def list_dead_letters(self) -> list[DeadLetterMessage]:
        return [
            _dead_letter_message_to_domain(dead_letter)
            for dead_letter in self._session.scalars(
                select(DbDeadLetterMessage).order_by(DbDeadLetterMessage.failed_at)
            ).all()
        ]


def _integration_message_to_domain(
    db_message: DbIntegrationMessage,
) -> IntegrationMessage:
    return IntegrationMessage(
        message_id=db_message.message_id,
        message_type=IntegrationMessageType(db_message.message_type),
        status=IntegrationMessageStatus(db_message.status),
        correlation_id=db_message.correlation_id,
        payload=dict(db_message.payload),
        attempt_count=db_message.attempt_count,
        max_attempts=db_message.max_attempts,
        next_retry_at=db_message.next_retry_at,
        last_error=db_message.last_error,
        published_at=db_message.published_at,
        created_at=db_message.created_at,
    )


def _dead_letter_message_to_domain(
    db_dead_letter: DbDeadLetterMessage,
) -> DeadLetterMessage:
    return DeadLetterMessage(
        dead_letter_id=db_dead_letter.dead_letter_id,
        original_message_id=db_dead_letter.original_message_id,
        message_type=IntegrationMessageType(db_dead_letter.message_type),
        correlation_id=db_dead_letter.correlation_id,
        payload=dict(db_dead_letter.payload),
        reason=db_dead_letter.reason,
        final_attempt_count=db_dead_letter.final_attempt_count,
        failed_at=db_dead_letter.failed_at,
    )


InMemoryIntegrationMessageRepository = IntegrationMessageRepository
