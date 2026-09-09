import logging
import time

from fastapi import FastAPI, Request

from app.core.correlation import (
    new_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from app.core.logging import log_event

logger = logging.getLogger(__name__)


def install_correlation_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()
        request.state.correlation_id = correlation_id
        token = set_correlation_id(correlation_id)
        started_at = time.perf_counter()

        log_event(
            logger,
            "request_started",
            method=request.method,
            path=request.url.path,
        )

        try:
            try:
                response = await call_next(request)
            except Exception:
                elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
                logger.exception(
                    "request_failed",
                    extra={
                        "extra_fields": {
                            "event": "request_failed",
                            "correlation_id": correlation_id,
                            "method": request.method,
                            "path": request.url.path,
                            "elapsed_ms": elapsed_ms,
                        }
                    },
                )
                raise

            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            response.headers["X-Correlation-ID"] = correlation_id
            log_event(
                logger,
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
            )

            return response
        finally:
            reset_correlation_id(token)
