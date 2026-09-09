from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class IntegrationMessageStatus(StrEnum):
    PENDING = "PENDING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    PUBLISHED = "PUBLISHED"
    DEAD_LETTERED = "DEAD_LETTERED"


class IntegrationMessageType(StrEnum):
    SHIPMENT_CONFIRMATION = "SHIPMENT_CONFIRMATION"


class DownstreamResult(StrEnum):
    SUCCESS = "SUCCESS"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"


@dataclass(frozen=True)
class IntegrationMessage:
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


@dataclass(frozen=True)
class DeadLetterMessage:
    dead_letter_id: str
    original_message_id: str
    message_type: IntegrationMessageType
    correlation_id: str
    payload: dict[str, object]
    reason: str
    final_attempt_count: int
    failed_at: datetime
