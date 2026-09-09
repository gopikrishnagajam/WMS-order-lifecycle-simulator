from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import DbPickTask, DbPickTaskLine
from app.orders.models import Order
from app.warehouse.models import PickTask, PickTaskLine, PickTaskStatus


class PickTaskNotFoundError(Exception):
    def __init__(self, pick_task_id: str) -> None:
        self.pick_task_id = pick_task_id
        super().__init__(f"Pick task not found: {pick_task_id}")


class PickTaskAlreadyCompletedError(Exception):
    def __init__(self, pick_task_id: str) -> None:
        self.pick_task_id = pick_task_id
        super().__init__(f"Pick task already completed: {pick_task_id}")


class DuplicatePickLineError(Exception):
    def __init__(self, order_line_id: str) -> None:
        self.order_line_id = order_line_id
        super().__init__(f"Duplicate pick line submitted: {order_line_id}")


class PickTaskLineMismatchError(Exception):
    pass


class PickQuantityExceededError(Exception):
    def __init__(
        self,
        order_line_id: str,
        picked_quantity: int,
        quantity_to_pick: int,
    ) -> None:
        self.order_line_id = order_line_id
        self.picked_quantity = picked_quantity
        self.quantity_to_pick = quantity_to_pick
        super().__init__(
            f"Picked quantity {picked_quantity} exceeds quantity to pick "
            f"{quantity_to_pick} for order line {order_line_id}"
        )


class PickTaskRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_for_order(self, order: Order) -> PickTask:
        db_pick_task = DbPickTask(
            pick_task_id=str(uuid4()),
            order_id=order.order_id,
            warehouse_id=order.warehouse_id,
            status=PickTaskStatus.OPEN,
            correlation_id=order.correlation_id,
            created_at=datetime.now(UTC),
            completed_at=None,
            lines=[
                DbPickTaskLine(
                    order_line_id=line.line_id,
                    sku=line.sku,
                    quantity_to_pick=line.allocated_quantity,
                    picked_quantity=0,
                )
                for line in order.lines
            ],
        )
        self._session.add(db_pick_task)
        self._session.flush()

        return _pick_task_to_domain(db_pick_task)

    def get(self, pick_task_id: str) -> PickTask | None:
        db_pick_task = self._get_db_pick_task(pick_task_id)
        if db_pick_task is None:
            return None

        return _pick_task_to_domain(db_pick_task)

    def list_tasks(self, order_id: str | None = None) -> list[PickTask]:
        statement = (
            select(DbPickTask)
            .options(selectinload(DbPickTask.lines))
            .order_by(DbPickTask.created_at)
        )
        if order_id is not None:
            statement = statement.where(DbPickTask.order_id == order_id)

        return [
            _pick_task_to_domain(pick_task)
            for pick_task in self._session.scalars(statement).all()
        ]

    def complete(
        self,
        pick_task_id: str,
        picked_quantities_by_order_line_id: dict[str, int],
    ) -> PickTask:
        db_pick_task = self._get_db_pick_task(pick_task_id)
        if db_pick_task is None:
            raise PickTaskNotFoundError(pick_task_id)

        if db_pick_task.status != PickTaskStatus.OPEN:
            raise PickTaskAlreadyCompletedError(pick_task_id)

        expected_line_ids = {line.order_line_id for line in db_pick_task.lines}
        submitted_line_ids = set(picked_quantities_by_order_line_id)
        if expected_line_ids != submitted_line_ids:
            raise PickTaskLineMismatchError

        for line in db_pick_task.lines:
            picked_quantity = picked_quantities_by_order_line_id[line.order_line_id]
            if picked_quantity > line.quantity_to_pick:
                raise PickQuantityExceededError(
                    order_line_id=line.order_line_id,
                    picked_quantity=picked_quantity,
                    quantity_to_pick=line.quantity_to_pick,
                )

            line.picked_quantity = picked_quantity

        db_pick_task.status = PickTaskStatus.COMPLETED
        if any(
            line.quantity_to_pick - line.picked_quantity > 0
            for line in db_pick_task.lines
        ):
            db_pick_task.status = PickTaskStatus.SHORT_PICK
        db_pick_task.completed_at = datetime.now(UTC)
        self._session.flush()

        return _pick_task_to_domain(db_pick_task)

    def _get_db_pick_task(self, pick_task_id: str) -> DbPickTask | None:
        return self._session.scalar(
            select(DbPickTask)
            .options(selectinload(DbPickTask.lines))
            .where(DbPickTask.pick_task_id == pick_task_id)
        )


def _pick_task_to_domain(db_pick_task: DbPickTask) -> PickTask:
    return PickTask(
        pick_task_id=db_pick_task.pick_task_id,
        order_id=db_pick_task.order_id,
        warehouse_id=db_pick_task.warehouse_id,
        status=PickTaskStatus(db_pick_task.status),
        lines=tuple(
            PickTaskLine(
                order_line_id=line.order_line_id,
                sku=line.sku,
                quantity_to_pick=line.quantity_to_pick,
                picked_quantity=line.picked_quantity,
            )
            for line in db_pick_task.lines
        ),
        correlation_id=db_pick_task.correlation_id,
        created_at=db_pick_task.created_at,
        completed_at=db_pick_task.completed_at,
    )


InMemoryPickTaskRepository = PickTaskRepository
