import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.integration.repository import IntegrationMessageRepository


@pytest.fixture(params=["sqlite", "postgres"])
def client(request):
    if request.param == "postgres":
        request.getfixturevalue("postgres_database")
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.state.db_engine.dispose()


def create_short_pick(client, lines=None, picked=None):
    lines = lines or [{"sku": "SKU-RED-SHIRT", "quantity": 3}]
    picked = picked if picked is not None else {"SKU-RED-SHIRT": 1}
    response = client.post("/orders", headers={"X-Idempotency-Key": "short-pick"}, json={
        "external_order_id": "OMS-SHORT", "warehouse_id": "WH-01", "lines": lines,
    })
    assert response.status_code == 201
    order = response.json()
    response = client.post(f"/warehouse/picks/{order['pick_task_id']}/complete", json={
        "lines": [{"order_line_id": line["line_id"],
                   "picked_quantity": picked[line["sku"]]} for line in order["lines"]],
    })
    assert response.status_code == 200
    return order


def resolve(client, order):
    return client.post(f"/orders/{order['order_id']}/resolve-short-pick",
                       json={"policy": "CANCEL_REMAINDER"})


def inventory(client, sku="SKU-RED-SHIRT"):
    return next(item for item in client.get("/inventory?warehouse_id=WH-01").json()
                if item["sku"] == sku)


def test_partial_resolution_ships_only_picked_and_reports_cancellations(client):
    order = create_short_pick(client, lines=[
        {"sku": "SKU-RED-SHIRT", "quantity": 3},
        {"sku": "SKU-BLUE-HAT", "quantity": 2},
    ], picked={"SKU-RED-SHIRT": 1, "SKU-BLUE-HAT": 0})
    assert client.post(f"/orders/{order['order_id']}/pack").status_code == 409
    response = resolve(client, order)
    assert response.status_code == 200
    assert response.json()["status"] == "SHORT_PICK_RESOLVED"
    assert sum(line["cancelled_quantity"] for line in response.json()["lines"]) == 4
    assert sum(line["quantity"] for line in response.json()["lines"]) == 5
    assert inventory(client)["allocated_quantity"] == 1
    assert inventory(client)["on_hand_quantity"] == 10
    assert inventory(client, "SKU-BLUE-HAT")["allocated_quantity"] == 0
    packed = client.post(f"/orders/{order['order_id']}/pack")
    assert packed.status_code == 200
    assert len(packed.json()["shipment"]["lines"]) == 1
    shipped = client.post(f"/orders/{order['order_id']}/ship", json={"carrier": "UPS"})
    assert shipped.status_code == 200
    message = shipped.json()["shipment_confirmation_message"]
    assert message["payload"]["lines"][0]["quantity"] == 1
    assert sum(line["quantity"] for line in message["payload"]["cancelled_lines"]) == 4
    assert inventory(client)["allocated_quantity"] == 0
    assert inventory(client)["on_hand_quantity"] == 9
    published = client.post(f"/integration/messages/{message['message_id']}/publish",
                            json={"downstream_result": "SUCCESS"})
    assert published.status_code == 200
    assert client.get(f"/orders/{order['order_id']}").json()["status"] == "CONFIRMATION_PUBLISHED"


def test_zero_pick_cancels_order_without_creating_shipment(client):
    order = create_short_pick(client, picked={"SKU-RED-SHIRT": 0})
    response = resolve(client, order)
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["lines"][0]["cancelled_quantity"] == 3
    assert inventory(client)["allocated_quantity"] == 0
    assert inventory(client)["on_hand_quantity"] == 10
    assert client.post(f"/orders/{order['order_id']}/pack").status_code == 409
    assert client.post(f"/orders/{order['order_id']}/ship", json={"carrier": "UPS"}).status_code == 409
    assert client.get("/shipments").json() == []
    assert client.get("/integration/messages").json() == []


def test_resolution_replay_does_not_release_twice_or_rewind_shipped_order(client):
    order = create_short_pick(client)
    first = resolve(client, order)
    assert resolve(client, order).json() == first.json()
    assert inventory(client)["allocated_quantity"] == 1
    client.post(f"/orders/{order['order_id']}/pack")
    client.post(f"/orders/{order['order_id']}/ship", json={"carrier": "UPS"})
    assert resolve(client, order).json()["status"] == "SHIPPED"
    assert inventory(client)["on_hand_quantity"] == 9
    assert inventory(client)["allocated_quantity"] == 0
    assert client.post(f"/orders/{order['order_id']}/ship", json={"carrier": "UPS"}).status_code == 409
    assert inventory(client)["on_hand_quantity"] == 9


def test_resolution_aggregates_duplicate_sku_lines(client):
    order = create_short_pick(client, lines=[
        {"sku": "SKU-RED-SHIRT", "quantity": 3},
        {"sku": "SKU-RED-SHIRT", "quantity": 2},
    ])
    response = resolve(client, order)
    assert response.status_code == 200
    assert sum(line["cancelled_quantity"] for line in response.json()["lines"]) == 3
    assert inventory(client)["allocated_quantity"] == 2


def test_resolution_rejects_missing_order_and_fully_picked_order(client):
    assert resolve(client, {"order_id": "missing"}).status_code == 404
    order = create_short_pick(client, picked={"SKU-RED-SHIRT": 3})
    before = inventory(client)
    assert resolve(client, order).status_code == 409
    assert inventory(client) == before


@pytest.mark.parametrize("body", [{}, {"policy": "BACKORDER"},
                                      {"policy": "CANCEL_REMAINDER", "quantity": 10}])
def test_resolution_rejects_unsupported_requests(client, body):
    order = create_short_pick(client)
    assert client.post(f"/orders/{order['order_id']}/resolve-short-pick", json=body).status_code == 422
    assert inventory(client)["allocated_quantity"] == 3


def test_ship_failure_rolls_back_inventory_shipment_and_order(client, monkeypatch):
    order = create_short_pick(client)
    resolve(client, order)
    client.post(f"/orders/{order['order_id']}/pack")
    before = inventory(client)

    def fail(*args, **kwargs):
        raise RuntimeError("Simulated outbox storage failure")

    monkeypatch.setattr(IntegrationMessageRepository, "create_shipment_confirmation", fail)
    response = client.post(f"/orders/{order['order_id']}/ship", json={"carrier": "UPS"})
    assert response.status_code == 500
    assert inventory(client) == before
    assert client.get(f"/orders/{order['order_id']}").json()["status"] == "PACKED"
    assert client.get("/shipments").json()[0]["status"] == "PACKED"
    assert client.get("/integration/messages").json() == []


def test_full_pick_shipping_consumes_stock(client):
    order = create_short_pick(client, picked={"SKU-RED-SHIRT": 3})
    client.post(f"/orders/{order['order_id']}/pack")
    response = client.post(f"/orders/{order['order_id']}/ship", json={"carrier": "UPS"})
    assert response.status_code == 200
    assert inventory(client)["on_hand_quantity"] == 7
    assert inventory(client)["allocated_quantity"] == 0
