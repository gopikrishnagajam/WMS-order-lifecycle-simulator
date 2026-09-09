from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import install_correlation_id_middleware
from app.db.session import (
    create_database_engine,
    create_session_factory,
    initialize_database,
    seed_inventory,
)
from app.fulfillment.router import router as fulfillment_router
from app.inventory.router import router as inventory_router
from app.integration.router import router as integration_router
from app.orders.router import router as orders_router
from app.warehouse.router import router as warehouse_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Simplified WMS order lifecycle and integration reliability simulator.",
        openapi_tags=[
            {
                "name": "system",
                "description": "Service health and runtime checks.",
            },
            {
                "name": "orders",
                "description": "OMS order intake, idempotency, and order lookup.",
            },
            {
                "name": "inventory",
                "description": "Seeded inventory visibility by SKU and warehouse.",
            },
            {
                "name": "warehouse",
                "description": "Warehouse pick task execution, including short picks.",
            },
            {
                "name": "fulfillment",
                "description": "Pack, ship, and shipment record operations.",
            },
            {
                "name": "integration",
                "description": "Shipment confirmation publishing, retry, and DLQ simulation.",
            },
        ],
    )
    install_correlation_id_middleware(app)

    web_directory = Path(__file__).parent / "web"
    app.mount("/assets", StaticFiles(directory=web_directory), name="assets")

    engine = create_database_engine(
        database_url=settings.database_url,
        echo=settings.database_echo,
    )
    if settings.database_auto_create_tables:
        initialize_database(engine)
    else:
        seed_inventory(engine)

    app.state.db_engine = engine
    app.state.session_factory = create_session_factory(engine)

    @app.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "environment": settings.environment,
        }

    @app.get("/health/ready", tags=["system"])
    def readiness_check() -> dict[str, str]:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is not reachable.",
            ) from exc

        return {
            "status": "ready",
            "database": "ok",
            "environment": settings.environment,
        }

    @app.get("/", include_in_schema=False)
    def operator_console() -> FileResponse:
        return FileResponse(web_directory / "index.html")

    app.include_router(inventory_router)
    app.include_router(orders_router)
    app.include_router(warehouse_router)
    app.include_router(fulfillment_router)
    app.include_router(integration_router)

    return app


app = create_app()
