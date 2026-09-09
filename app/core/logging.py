import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.correlation import get_correlation_id


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(log_level: str) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    if any(getattr(handler, "_wms_json_handler", False) for handler in root_logger.handlers):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler._wms_json_handler = True  # type: ignore[attr-defined]
    root_logger.addHandler(handler)


def log_event(
    logger: logging.Logger,
    event: str,
    **fields: object,
) -> None:
    correlation_id = get_correlation_id()
    extra_fields = {"event": event, **fields}
    if correlation_id is not None:
        extra_fields["correlation_id"] = correlation_id

    logger.info(event, extra={"extra_fields": extra_fields})

