from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.fulfillment.dependencies import get_fulfillment_service
from app.fulfillment.models import Shipment, ShipmentLine
from app.fulfillment.repository import (
    ShipmentNotFoundError,
    ShipmentNotFoundForOrderError,
)
from app.fulfillment.schemas import (
    PackOrderResponse,
    ShipOrderRequest,
    ShipOrderResponse,
    ShipmentLineResponse,
    ShipmentResponse,
)
from app.fulfillment.service import (
    FulfillmentOrderSyncError,
    FulfillmentService,
    OrderCannotBePackedError,
    OrderCannotBeShippedError,
    OrderNotFoundError,
    ShortPickCannotBePackedError,
)
from app.integration.router import integration_message_to_response
from app.orders.repository import order_to_response

router = APIRouter(tags=["fulfillment"])


@router.get("/shipments", response_model=list[ShipmentResponse])
def list_shipments(
    fulfillment_service: Annotated[
        FulfillmentService,
        Depends(get_fulfillment_service),
    ],
    order_id: Annotated[str | None, Query(min_length=1)] = None,
) -> list[ShipmentResponse]:
    return [
        shipment_to_response(shipment)
        for shipment in fulfillment_service.list_shipments(order_id=order_id)
    ]


@router.get("/shipments/{shipment_id}", response_model=ShipmentResponse)
def get_shipment(
    shipment_id: str,
    fulfillment_service: Annotated[
        FulfillmentService,
        Depends(get_fulfillment_service),
    ],
) -> ShipmentResponse:
    shipment = fulfillment_service.get_shipment(shipment_id)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found.",
        )

    return shipment_to_response(shipment)


@router.post("/orders/{order_id}/pack", response_model=PackOrderResponse)
def pack_order(
    order_id: str,
    fulfillment_service: Annotated[
        FulfillmentService,
        Depends(get_fulfillment_service),
    ],
) -> PackOrderResponse:
    try:
        order, shipment = fulfillment_service.pack_order(order_id)
    except OrderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        ) from exc
    except ShortPickCannotBePackedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Short-pick orders cannot be packed until the shortage is resolved.",
        ) from exc
    except OrderCannotBePackedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only PICKED orders can be packed. Current status: {exc.current_status}.",
        ) from exc
    except FulfillmentOrderSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shipment was created but order status could not be updated.",
        ) from exc

    return PackOrderResponse(
        order=order_to_response(order),
        shipment=shipment_to_response(shipment),
    )


@router.post("/orders/{order_id}/ship", response_model=ShipOrderResponse)
def ship_order(
    order_id: str,
    request: ShipOrderRequest,
    fulfillment_service: Annotated[
        FulfillmentService,
        Depends(get_fulfillment_service),
    ],
) -> ShipOrderResponse:
    try:
        order, shipment, message = fulfillment_service.ship_order(
            order_id=order_id,
            request=request,
        )
    except OrderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        ) from exc
    except ShipmentNotFoundForOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found for order.",
        ) from exc
    except OrderCannotBeShippedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only PACKED orders can be shipped. Current status: {exc.current_status}.",
        ) from exc
    except FulfillmentOrderSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shipment was shipped but order status could not be updated.",
        ) from exc

    return ShipOrderResponse(
        order=order_to_response(order),
        shipment=shipment_to_response(shipment),
        shipment_confirmation_message=integration_message_to_response(message),
    )


def shipment_to_response(shipment: Shipment) -> ShipmentResponse:
    return ShipmentResponse(
        shipment_id=shipment.shipment_id,
        order_id=shipment.order_id,
        warehouse_id=shipment.warehouse_id,
        status=shipment.status,
        lines=[shipment_line_to_response(line) for line in shipment.lines],
        correlation_id=shipment.correlation_id,
        packed_at=shipment.packed_at,
        shipped_at=shipment.shipped_at,
        carrier=shipment.carrier,
        tracking_number=shipment.tracking_number,
    )


def shipment_line_to_response(line: ShipmentLine) -> ShipmentLineResponse:
    return ShipmentLineResponse(
        order_line_id=line.order_line_id,
        sku=line.sku,
        quantity=line.quantity,
    )

