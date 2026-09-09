from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.warehouse.dependencies import get_warehouse_service
from app.warehouse.models import PickTask, PickTaskLine
from app.warehouse.repository import (
    DuplicatePickLineError,
    PickQuantityExceededError,
    PickTaskAlreadyCompletedError,
    PickTaskNotFoundError,
    PickTaskLineMismatchError,
)
from app.warehouse.schemas import (
    CompletePickTaskRequest,
    CompletePickTaskResponse,
    PickTaskLineResponse,
    PickTaskResponse,
)
from app.warehouse.service import WarehouseOrderSyncError, WarehouseService

router = APIRouter(prefix="/warehouse", tags=["warehouse"])


@router.get("/picks", response_model=list[PickTaskResponse])
def list_pick_tasks(
    warehouse_service: Annotated[WarehouseService, Depends(get_warehouse_service)],
    order_id: Annotated[str | None, Query(min_length=1)] = None,
) -> list[PickTaskResponse]:
    return [
        pick_task_to_response(pick_task)
        for pick_task in warehouse_service.list_pick_tasks(order_id=order_id)
    ]


@router.get("/picks/{pick_task_id}", response_model=PickTaskResponse)
def get_pick_task(
    pick_task_id: str,
    warehouse_service: Annotated[WarehouseService, Depends(get_warehouse_service)],
) -> PickTaskResponse:
    pick_task = warehouse_service.get_pick_task(pick_task_id)
    if pick_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pick task not found.",
        )

    return pick_task_to_response(pick_task)


@router.post(
    "/picks/{pick_task_id}/complete",
    response_model=CompletePickTaskResponse,
)
def complete_pick_task(
    pick_task_id: str,
    request: CompletePickTaskRequest,
    warehouse_service: Annotated[WarehouseService, Depends(get_warehouse_service)],
) -> CompletePickTaskResponse:
    try:
        pick_task, order = warehouse_service.complete_pick_task(
            pick_task_id=pick_task_id,
            request=request,
        )
    except DuplicatePickLineError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Duplicate pick line submitted: {exc.order_line_id}.",
        ) from exc
    except PickTaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pick task not found.",
        ) from exc
    except PickTaskLineMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pick completion lines must match the task order lines.",
        ) from exc
    except PickQuantityExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Picked quantity for order line {exc.order_line_id} cannot exceed "
                f"quantity to pick {exc.quantity_to_pick}."
            ),
        ) from exc
    except PickTaskAlreadyCompletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pick task has already been completed.",
        ) from exc
    except WarehouseOrderSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pick task completed but order status could not be updated.",
        ) from exc

    return CompletePickTaskResponse(
        pick_task=pick_task_to_response(pick_task),
        order_id=order.order_id,
        order_status=order.status,
    )


def pick_task_to_response(pick_task: PickTask) -> PickTaskResponse:
    return PickTaskResponse(
        pick_task_id=pick_task.pick_task_id,
        order_id=pick_task.order_id,
        warehouse_id=pick_task.warehouse_id,
        status=pick_task.status,
        lines=[pick_task_line_to_response(line) for line in pick_task.lines],
        correlation_id=pick_task.correlation_id,
        created_at=pick_task.created_at,
        completed_at=pick_task.completed_at,
    )


def pick_task_line_to_response(line: PickTaskLine) -> PickTaskLineResponse:
    return PickTaskLineResponse(
        order_line_id=line.order_line_id,
        sku=line.sku,
        quantity_to_pick=line.quantity_to_pick,
        picked_quantity=line.picked_quantity,
        short_quantity=line.short_quantity,
    )
