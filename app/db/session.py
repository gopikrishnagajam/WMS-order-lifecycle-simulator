from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, DbInventoryItem
from app.inventory.models import InventoryItem


def create_database_engine(database_url: str, echo: bool = False) -> Engine:
    engine_options: dict[str, object] = {
        "echo": echo,
        "future": True,
    }
    if database_url.startswith("sqlite"):
        engine_options["connect_args"] = {"check_same_thread": False}
        if database_url.endswith(":memory:"):
            engine_options["poolclass"] = StaticPool

    return create_engine(database_url, **engine_options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    seed_inventory(engine)


def seed_inventory(engine: Engine) -> None:
    """Seed demo stock once, including when Alembic manages the schema."""

    with Session(engine) as session:
        _seed_inventory(session)
        session.commit()


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _seed_inventory(session: Session) -> None:
    has_inventory = session.scalar(select(DbInventoryItem).limit(1)) is not None
    if has_inventory:
        return

    session.add_all(
        [
            _db_inventory_item(item)
            for item in [
                InventoryItem(
                    sku="SKU-RED-SHIRT",
                    warehouse_id="WH-01",
                    description="Red shirt",
                    on_hand_quantity=10,
                ),
                InventoryItem(
                    sku="SKU-BLUE-HAT",
                    warehouse_id="WH-01",
                    description="Blue hat",
                    on_hand_quantity=5,
                ),
                InventoryItem(
                    sku="SKU-GREEN-SOCKS",
                    warehouse_id="WH-01",
                    description="Green socks",
                    on_hand_quantity=20,
                ),
                InventoryItem(
                    sku="SKU-RED-SHIRT",
                    warehouse_id="WH-02",
                    description="Red shirt",
                    on_hand_quantity=4,
                ),
            ]
        ]
    )


def _db_inventory_item(item: InventoryItem) -> DbInventoryItem:
    return DbInventoryItem(
        sku=item.sku,
        warehouse_id=item.warehouse_id,
        description=item.description,
        on_hand_quantity=item.on_hand_quantity,
        allocated_quantity=item.allocated_quantity,
    )
