from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.fulfillment.repository import ShipmentRepository
from app.fulfillment.service import FulfillmentService
from app.inventory.repository import InventoryRepository
from app.integration.repository import IntegrationMessageRepository
from app.integration.service import IntegrationService
from app.orders.repository import OrderRepository
from app.orders.service import OrderService
from app.warehouse.repository import PickTaskRepository
from app.warehouse.service import WarehouseService


def get_order_repository(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> OrderRepository:
    return OrderRepository(session)


def get_inventory_repository(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> InventoryRepository:
    return InventoryRepository(session)


def get_pick_task_repository(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> PickTaskRepository:
    return PickTaskRepository(session)


def get_shipment_repository(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> ShipmentRepository:
    return ShipmentRepository(session)


def get_integration_message_repository(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> IntegrationMessageRepository:
    return IntegrationMessageRepository(session)


def get_order_service(
    order_repository: Annotated[OrderRepository, Depends(get_order_repository)],
    inventory_repository: Annotated[
        InventoryRepository,
        Depends(get_inventory_repository),
    ],
    pick_task_repository: Annotated[
        PickTaskRepository,
        Depends(get_pick_task_repository),
    ],
) -> OrderService:
    return OrderService(
        order_repository=order_repository,
        inventory_repository=inventory_repository,
        pick_task_repository=pick_task_repository,
    )


def get_warehouse_service(
    pick_task_repository: Annotated[
        PickTaskRepository,
        Depends(get_pick_task_repository),
    ],
    order_repository: Annotated[OrderRepository, Depends(get_order_repository)],
) -> WarehouseService:
    return WarehouseService(
        pick_task_repository=pick_task_repository,
        order_repository=order_repository,
    )


def get_fulfillment_service(
    order_repository: Annotated[OrderRepository, Depends(get_order_repository)],
    shipment_repository: Annotated[
        ShipmentRepository,
        Depends(get_shipment_repository),
    ],
    integration_message_repository: Annotated[
        IntegrationMessageRepository,
        Depends(get_integration_message_repository),
    ],
    inventory_repository: Annotated[InventoryRepository, Depends(get_inventory_repository)],
) -> FulfillmentService:
    return FulfillmentService(
        order_repository=order_repository,
        shipment_repository=shipment_repository,
        integration_message_repository=integration_message_repository,
        inventory_repository=inventory_repository,
    )


def get_integration_service(
    integration_message_repository: Annotated[
        IntegrationMessageRepository,
        Depends(get_integration_message_repository),
    ],
    order_repository: Annotated[OrderRepository, Depends(get_order_repository)],
) -> IntegrationService:
    return IntegrationService(
        integration_message_repository=integration_message_repository,
        order_repository=order_repository,
    )
