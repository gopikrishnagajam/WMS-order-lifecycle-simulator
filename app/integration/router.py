from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.integration.dependencies import get_integration_service
from app.integration.models import DeadLetterMessage, IntegrationMessage
from app.integration.schemas import (
    DeadLetterMessageResponse,
    IntegrationMessageResponse,
    ProcessIntegrationMessageRequest,
    ProcessIntegrationMessageResponse,
)
from app.integration.service import (
    IntegrationMessageFinalizedError,
    IntegrationMessageNotFoundError,
    IntegrationOrderSyncError,
    IntegrationService,
)

router = APIRouter(prefix="/integration", tags=["integration"])


@router.get("/messages", response_model=list[IntegrationMessageResponse])
def list_integration_messages(
    integration_service: Annotated[
        IntegrationService,
        Depends(get_integration_service),
    ],
) -> list[IntegrationMessageResponse]:
    return [
        integration_message_to_response(message)
        for message in integration_service.list_messages()
    ]


@router.post(
    "/messages/{message_id}/publish",
    response_model=ProcessIntegrationMessageResponse,
)
def publish_integration_message(
    message_id: str,
    request: ProcessIntegrationMessageRequest,
    integration_service: Annotated[
        IntegrationService,
        Depends(get_integration_service),
    ],
) -> ProcessIntegrationMessageResponse:
    return _process_integration_message(
        message_id=message_id,
        request=request,
        integration_service=integration_service,
    )


@router.post(
    "/messages/{message_id}/retry",
    response_model=ProcessIntegrationMessageResponse,
)
def retry_integration_message(
    message_id: str,
    request: ProcessIntegrationMessageRequest,
    integration_service: Annotated[
        IntegrationService,
        Depends(get_integration_service),
    ],
) -> ProcessIntegrationMessageResponse:
    return _process_integration_message(
        message_id=message_id,
        request=request,
        integration_service=integration_service,
    )


@router.get("/dlq", response_model=list[DeadLetterMessageResponse])
def list_dead_letter_messages(
    integration_service: Annotated[
        IntegrationService,
        Depends(get_integration_service),
    ],
) -> list[DeadLetterMessageResponse]:
    return [
        dead_letter_message_to_response(dead_letter)
        for dead_letter in integration_service.list_dead_letters()
    ]


def _process_integration_message(
    message_id: str,
    request: ProcessIntegrationMessageRequest,
    integration_service: IntegrationService,
) -> ProcessIntegrationMessageResponse:
    try:
        result = integration_service.process_message(
            message_id=message_id,
            request=request,
        )
    except IntegrationMessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration message not found.",
        ) from exc
    except IntegrationMessageFinalizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Integration message is already finalized with status {exc.status}.",
        ) from exc
    except IntegrationOrderSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Integration message published but order status could not be updated.",
        ) from exc

    return ProcessIntegrationMessageResponse(
        message=integration_message_to_response(result.message),
        order_status=result.order_status,
        dead_letter=(
            dead_letter_message_to_response(result.dead_letter)
            if result.dead_letter is not None
            else None
        ),
    )


def integration_message_to_response(
    message: IntegrationMessage,
) -> IntegrationMessageResponse:
    return IntegrationMessageResponse(
        message_id=message.message_id,
        message_type=message.message_type,
        status=message.status,
        correlation_id=message.correlation_id,
        payload=message.payload,
        attempt_count=message.attempt_count,
        max_attempts=message.max_attempts,
        next_retry_at=message.next_retry_at,
        last_error=message.last_error,
        published_at=message.published_at,
        created_at=message.created_at,
    )


def dead_letter_message_to_response(
    dead_letter: DeadLetterMessage,
) -> DeadLetterMessageResponse:
    return DeadLetterMessageResponse(
        dead_letter_id=dead_letter.dead_letter_id,
        original_message_id=dead_letter.original_message_id,
        message_type=dead_letter.message_type,
        correlation_id=dead_letter.correlation_id,
        payload=dead_letter.payload,
        reason=dead_letter.reason,
        final_attempt_count=dead_letter.final_attempt_count,
        failed_at=dead_letter.failed_at,
    )
