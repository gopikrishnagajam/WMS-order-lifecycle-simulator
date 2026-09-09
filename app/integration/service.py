import logging
from dataclasses import dataclass

from app.core.logging import log_event
from app.integration.models import (
    DeadLetterMessage,
    DownstreamResult,
    IntegrationMessage,
    IntegrationMessageStatus,
)
from app.integration.repository import IntegrationMessageRepository
from app.integration.schemas import ProcessIntegrationMessageRequest
from app.orders.models import OrderStatus
from app.orders.repository import OrderRepository

logger = logging.getLogger(__name__)


class IntegrationMessageNotFoundError(Exception):
    def __init__(self, message_id: str) -> None:
        self.message_id = message_id
        super().__init__(f"Integration message not found: {message_id}")


class IntegrationMessageFinalizedError(Exception):
    def __init__(
        self,
        message_id: str,
        status: IntegrationMessageStatus,
    ) -> None:
        self.message_id = message_id
        self.status = status
        super().__init__(f"Integration message already finalized: {message_id}")


class IntegrationOrderSyncError(Exception):
    pass


@dataclass(frozen=True)
class ProcessIntegrationMessageResult:
    message: IntegrationMessage
    order_status: OrderStatus | None
    dead_letter: DeadLetterMessage | None


class IntegrationService:
    def __init__(
        self,
        integration_message_repository: IntegrationMessageRepository,
        order_repository: OrderRepository,
    ) -> None:
        self._integration_message_repository = integration_message_repository
        self._order_repository = order_repository

    def list_messages(self) -> list[IntegrationMessage]:
        return self._integration_message_repository.list_messages()

    def list_dead_letters(self) -> list[DeadLetterMessage]:
        return self._integration_message_repository.list_dead_letters()

    def process_message(
        self,
        message_id: str,
        request: ProcessIntegrationMessageRequest,
    ) -> ProcessIntegrationMessageResult:
        message = self._get_processable_message_or_raise(message_id)

        if request.downstream_result == DownstreamResult.SUCCESS:
            return self._mark_published(message)

        if request.downstream_result == DownstreamResult.TRANSIENT_FAILURE:
            return self._handle_transient_failure(message, request)

        return self._dead_letter(
            message=message,
            reason=(
                request.error_message
                or "Permanent OMS failure while publishing shipment confirmation."
            ),
            count_attempt=True,
        )

    def _mark_published(
        self,
        message: IntegrationMessage,
    ) -> ProcessIntegrationMessageResult:
        published_message = self._integration_message_repository.mark_published(
            message.message_id
        )
        if published_message is None:
            raise IntegrationMessageNotFoundError(message.message_id)

        order_id = str(published_message.payload["order_id"])
        order = self._order_repository.update_status(
            order_id=order_id,
            status=OrderStatus.CONFIRMATION_PUBLISHED,
        )
        if order is None:
            raise IntegrationOrderSyncError

        log_event(
            logger,
            "integration_message_published",
            message_id=published_message.message_id,
            order_id=order.order_id,
            attempt_count=published_message.attempt_count,
            status=published_message.status,
            order_status=order.status,
        )

        return ProcessIntegrationMessageResult(
            message=published_message,
            order_status=order.status,
            dead_letter=None,
        )

    def _handle_transient_failure(
        self,
        message: IntegrationMessage,
        request: ProcessIntegrationMessageRequest,
    ) -> ProcessIntegrationMessageResult:
        error_message = (
            request.error_message
            or "Transient OMS failure while publishing shipment confirmation."
        )

        if message.attempt_count + 1 >= message.max_attempts:
            return self._dead_letter(
                message=message,
                reason=f"Max attempts reached after transient failure: {error_message}",
                count_attempt=True,
            )

        retry_message = self._integration_message_repository.schedule_retry(
            message_id=message.message_id,
            error_message=error_message,
        )
        if retry_message is None:
            raise IntegrationMessageNotFoundError(message.message_id)

        log_event(
            logger,
            "integration_message_retry_scheduled",
            message_id=retry_message.message_id,
            attempt_count=retry_message.attempt_count,
            max_attempts=retry_message.max_attempts,
            next_retry_at=retry_message.next_retry_at,
            status=retry_message.status,
        )

        return ProcessIntegrationMessageResult(
            message=retry_message,
            order_status=None,
            dead_letter=None,
        )

    def _dead_letter(
        self,
        message: IntegrationMessage,
        reason: str,
        count_attempt: bool,
    ) -> ProcessIntegrationMessageResult:
        dead_letter_result = self._integration_message_repository.dead_letter(
            message_id=message.message_id,
            reason=reason,
            count_attempt=count_attempt,
        )
        if dead_letter_result is None:
            raise IntegrationMessageNotFoundError(message.message_id)

        dead_lettered_message, dead_letter = dead_letter_result
        log_event(
            logger,
            "integration_message_dead_lettered",
            message_id=dead_lettered_message.message_id,
            dead_letter_id=dead_letter.dead_letter_id,
            attempt_count=dead_lettered_message.attempt_count,
            status=dead_lettered_message.status,
            reason=dead_letter.reason,
        )

        return ProcessIntegrationMessageResult(
            message=dead_lettered_message,
            order_status=None,
            dead_letter=dead_letter,
        )

    def _get_processable_message_or_raise(
        self,
        message_id: str,
    ) -> IntegrationMessage:
        message = self._integration_message_repository.get(message_id)
        if message is None:
            raise IntegrationMessageNotFoundError(message_id)

        if message.status in {
            IntegrationMessageStatus.PUBLISHED,
            IntegrationMessageStatus.DEAD_LETTERED,
        }:
            raise IntegrationMessageFinalizedError(
                message_id=message_id,
                status=message.status,
            )

        return message
