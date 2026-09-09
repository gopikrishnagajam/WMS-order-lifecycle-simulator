from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.integration.models import (
    DownstreamResult,
    IntegrationMessageStatus,
    IntegrationMessageType,
)
from app.orders.models import OrderStatus


class IntegrationMessageResponse(BaseModel):
    message_id: str
    message_type: IntegrationMessageType
    status: IntegrationMessageStatus
    correlation_id: str
    payload: dict[str, object]
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None
    last_error: str | None
    published_at: datetime | None
    created_at: datetime


class ProcessIntegrationMessageRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "downstream_result": "SUCCESS",
                },
                {
                    "downstream_result": "TRANSIENT_FAILURE",
                    "error_message": "OMS timeout",
                },
                {
                    "downstream_result": "PERMANENT_FAILURE",
                    "error_message": "OMS rejected payload",
                },
            ]
        }
    )

    downstream_result: DownstreamResult = Field(
        default=DownstreamResult.SUCCESS,
        examples=["SUCCESS"],
    )
    error_message: str | None = Field(default=None, examples=["OMS timeout"])


class DeadLetterMessageResponse(BaseModel):
    dead_letter_id: str
    original_message_id: str
    message_type: IntegrationMessageType
    correlation_id: str
    payload: dict[str, object]
    reason: str
    final_attempt_count: int
    failed_at: datetime


class ProcessIntegrationMessageResponse(BaseModel):
    message: IntegrationMessageResponse
    order_status: OrderStatus | None
    dead_letter: DeadLetterMessageResponse | None
