from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main import create_app


def create_order(client, key, quantity):
    return client.post("/orders", headers={"X-Idempotency-Key": key}, json={
        "external_order_id": key, "warehouse_id": "WH-01",
        "lines": [{"sku": "SKU-RED-SHIRT", "quantity": quantity}],
    })


def test_concurrent_allocations_cannot_oversell(postgres_database):
    app = create_app()
    barrier = Barrier(2)

    def allocate(key):
        with TestClient(app) as client:
            barrier.wait(timeout=10)
            return create_order(client, key, 7).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(allocate, ["first", "second"])) == [201, 409]
        with TestClient(app) as client:
            item = next(i for i in client.get("/inventory?warehouse_id=WH-01").json()
                        if i["sku"] == "SKU-RED-SHIRT")
            assert item["allocated_quantity"] == 7
            assert item["available_quantity"] == 3
            assert len(client.get("/warehouse/picks").json()) == 1
    finally:
        app.state.db_engine.dispose()


def test_concurrent_resolution_releases_inventory_once(postgres_database):
    app = create_app()
    try:
        with TestClient(app) as client:
            order = create_order(client, "concurrent-resolution", 3).json()
            client.post(f"/warehouse/picks/{order['pick_task_id']}/complete", json={
                "lines": [{"order_line_id": order["lines"][0]["line_id"], "picked_quantity": 1}],
            })
        barrier = Barrier(2)

        def resolve(_):
            with TestClient(app) as client:
                barrier.wait(timeout=10)
                return client.post(f"/orders/{order['order_id']}/resolve-short-pick",
                                   json={"policy": "CANCEL_REMAINDER"})

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(resolve, range(2)))
        assert all(r.status_code == 200 for r in responses)
        assert responses[0].json() == responses[1].json()
        with TestClient(app) as client:
            item = next(i for i in client.get("/inventory?warehouse_id=WH-01").json()
                        if i["sku"] == "SKU-RED-SHIRT")
            assert item["allocated_quantity"] == 1
    finally:
        app.state.db_engine.dispose()


def test_resolved_order_and_shipment_survive_app_restart(postgres_database):
    first = create_app()
    second = None
    try:
        with TestClient(first) as client:
            order = create_order(client, "restart", 3).json()
            client.post(f"/warehouse/picks/{order['pick_task_id']}/complete", json={
                "lines": [{"order_line_id": order["lines"][0]["line_id"], "picked_quantity": 1}],
            })
            assert client.post(f"/orders/{order['order_id']}/resolve-short-pick",
                               json={"policy": "CANCEL_REMAINDER"}).status_code == 200
        first.state.db_engine.dispose()
        second = create_app()
        with TestClient(second) as client:
            persisted = client.get(f"/orders/{order['order_id']}").json()
            assert persisted["status"] == "SHORT_PICK_RESOLVED"
            assert persisted["lines"][0]["cancelled_quantity"] == 2
            assert client.post(f"/orders/{order['order_id']}/pack").status_code == 200
            shipment = client.post(f"/orders/{order['order_id']}/ship", json={"carrier": "UPS"})
            assert shipment.status_code == 200
            message_id = shipment.json()["shipment_confirmation_message"]["message_id"]
        second.state.db_engine.dispose()
        with TestClient(first) as client:
            assert client.get(f"/orders/{order['order_id']}").json()["status"] == "SHIPPED"
            assert client.get("/shipments").json()[0]["lines"][0]["quantity"] == 1
            assert client.get("/integration/messages").json()[0]["message_id"] == message_id
            assert client.post(f"/integration/messages/{message_id}/publish",
                               json={"downstream_result": "SUCCESS"}).status_code == 200
    finally:
        first.state.db_engine.dispose()
        if second is not None:
            second.state.db_engine.dispose()


def test_migration_preserves_old_orders_and_reconciles_shipped_stock(postgres_database):
    config = Config("alembic.ini")
    command.downgrade(config, "20260908_0001")
    engine = create_engine(postgres_database)
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO inventory_items VALUES ('SKU-RED-SHIRT', 'WH-01', 'Red shirt', 10, 3);
                INSERT INTO orders (order_id, external_order_id, warehouse_id, status,
                    correlation_id, idempotency_key, request_fingerprint, created_at)
                VALUES ('old-order', 'OMS-OLD', 'WH-01', 'SHIPPED', 'corr', 'old-key', 'hash', now());
                INSERT INTO order_lines VALUES ('old-line', 'old-order', 'SKU-RED-SHIRT', 3, 3, 3);
                INSERT INTO shipments (shipment_id, order_id, warehouse_id, status,
                    correlation_id, packed_at, shipped_at)
                VALUES ('old-shipment', 'old-order', 'WH-01', 'SHIPPED', 'corr', now(), now());
                INSERT INTO shipment_lines VALUES ('old-shipment', 'old-line', 'SKU-RED-SHIRT', 3);
            """))
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT cancelled_quantity FROM order_lines")).scalar_one() == 0
            assert connection.execute(text("SELECT on_hand_quantity, allocated_quantity FROM inventory_items")).one() == (7, 0)
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT on_hand_quantity FROM inventory_items")).scalar_one() == 7
        command.downgrade(config, "20260908_0001")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT on_hand_quantity, allocated_quantity FROM inventory_items")).one() == (10, 3)
    finally:
        engine.dispose()
