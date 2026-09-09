from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.core.correlation import get_correlation_id, new_correlation_id
from app.inventory.repository import (
    InsufficientInventoryError,
    InventoryNotStockedError,
    UnknownSkuError,
    UnknownWarehouseError,
)
from app.orders.dependencies import get_order_service
from app.orders.repository import (
    IdempotencyConflictError,
    order_to_response,
)
from app.orders.schemas import OrderCreate, OrderResponse, ResolveShortPickRequest
from app.orders.service import (
    OrderService,
    OrderCannotResolveShortPickError,
    ShortPickOrderNotFoundError,
)

router = APIRouter(tags=["orders"])


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    order_request: OrderCreate,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="X-Idempotency-Key", min_length=1),
    ],
    order_service: Annotated[OrderService, Depends(get_order_service)],
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID"),
    ] = None,
) -> OrderResponse:
    effective_correlation_id = (
        correlation_id or get_correlation_id() or new_correlation_id()
    )

    try:
        result = order_service.create_order(
            order_request=order_request,
            idempotency_key=idempotency_key,
            correlation_id=effective_correlation_id,
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was already used with a different order request.",
        ) from exc
    except UnknownWarehouseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown warehouse: {exc.warehouse_id}.",
        ) from exc
    except UnknownSkuError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown SKU: {exc.sku}.",
        ) from exc
    except InventoryNotStockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SKU {exc.sku} is not stocked at warehouse {exc.warehouse_id}.",
        ) from exc
    except InsufficientInventoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Insufficient inventory for SKU {exc.sku} at warehouse "
                f"{exc.warehouse_id}: requested {exc.requested_quantity}, "
                f"available {exc.available_quantity}."
            ),
        ) from exc

    if result.replayed:
        response.status_code = status.HTTP_200_OK

    return order_to_response(result.order, replayed=result.replayed)


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: str,
    order_service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderResponse:
    order = order_service.get_order(order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    return order_to_response(order)


@router.get("/orders", response_model=list[OrderResponse])
def list_orders(
    order_service: Annotated[OrderService, Depends(get_order_service)],
) -> list[OrderResponse]:
    return [order_to_response(order) for order in order_service.list_orders()]


@router.post("/orders/{order_id}/resolve-short-pick", response_model=OrderResponse)
def resolve_short_pick(
    order_id: str,
    request: ResolveShortPickRequest,
    order_service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderResponse:
    """Cancel unpicked units and allow fulfillment of the picked remainder."""
    try:
        order = order_service.resolve_short_pick(order_id)
    except ShortPickOrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Order not found.") from exc
    except OrderCannotResolveShortPickError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return order_to_response(order)
