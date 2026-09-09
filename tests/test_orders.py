from fastapi.testclient import TestClient

from app.main import create_app


def test_create_order_returns_picking_order() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/orders",
        headers={
            "X-Idempotency-Key": "idem-order-1001",
            "X-Correlation-ID": "corr-order-1001",
        },
        json={
            "external_order_id": "OMS-1001",
            "warehouse_id": "WH-01",
            "customer_id": "CUST-01",
            "lines": [
                {
                    "sku": "SKU-RED-SHIRT",
                    "quantity": 2,
                }
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["order_id"]
    assert body["external_order_id"] == "OMS-1001"
    assert body["warehouse_id"] == "WH-01"
    assert body["customer_id"] == "CUST-01"
    assert body["status"] == "PICKING"
    assert body["pick_task_id"]
    assert body["correlation_id"] == "corr-order-1001"
    assert body["idempotency_key"] == "idem-order-1001"
    assert body["idempotency_replayed"] is False
    assert body["lines"][0]["sku"] == "SKU-RED-SHIRT"
    assert body["lines"][0]["quantity"] == 2
    assert body["lines"][0]["allocated_quantity"] == 2
    assert body["lines"][0]["picked_quantity"] == 0


def test_get_order_returns_created_order() -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-order-1002"},
        json={
            "external_order_id": "OMS-1002",
            "warehouse_id": "WH-01",
            "lines": [{"sku": "SKU-BLUE-HAT", "quantity": 1}],
        },
    )
    order_id = create_response.json()["order_id"]

    response = client.get(f"/orders/{order_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == order_id
    assert body["external_order_id"] == "OMS-1002"
    assert body["status"] == "PICKING"
    assert body["pick_task_id"]


def test_duplicate_order_with_same_idempotency_key_replays_original_order() -> None:
    client = TestClient(create_app())
    payload = {
        "external_order_id": "OMS-1003",
        "warehouse_id": "WH-01",
        "lines": [{"sku": "SKU-GREEN-SOCKS", "quantity": 3}],
    }

    first_response = client.post(
        "/orders",
        headers={
            "X-Idempotency-Key": "idem-order-1003",
            "X-Correlation-ID": "corr-original",
        },
        json=payload,
    )
    second_response = client.post(
        "/orders",
        headers={
            "X-Idempotency-Key": "idem-order-1003",
            "X-Correlation-ID": "corr-duplicate",
        },
        json=payload,
    )

    first_body = first_response.json()
    second_body = second_response.json()
    assert first_response.status_code == 201
    assert second_response.status_code == 200
    assert second_body["order_id"] == first_body["order_id"]
    assert second_body["correlation_id"] == "corr-original"
    assert second_body["idempotency_replayed"] is True


def test_duplicate_order_does_not_allocate_inventory_twice() -> None:
    client = TestClient(create_app())
    payload = {
        "external_order_id": "OMS-1007",
        "warehouse_id": "WH-01",
        "lines": [{"sku": "SKU-GREEN-SOCKS", "quantity": 3}],
    }

    client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-order-1007"},
        json=payload,
    )
    client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-order-1007"},
        json=payload,
    )

    inventory_response = client.get("/inventory", params={"warehouse_id": "WH-01"})
    green_socks = _find_inventory_item(
        inventory_response.json(),
        warehouse_id="WH-01",
        sku="SKU-GREEN-SOCKS",
    )
    assert green_socks["on_hand_quantity"] == 20
    assert green_socks["allocated_quantity"] == 3
    assert green_socks["available_quantity"] == 17


def test_reused_idempotency_key_with_different_payload_returns_conflict() -> None:
    client = TestClient(create_app())

    client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-conflict"},
        json={
            "external_order_id": "OMS-1004",
            "warehouse_id": "WH-01",
            "lines": [{"sku": "SKU-BLUE-HAT", "quantity": 1}],
        },
    )

    response = client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-conflict"},
        json={
            "external_order_id": "OMS-1004",
            "warehouse_id": "WH-01",
            "lines": [{"sku": "SKU-BLUE-HAT", "quantity": 2}],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Idempotency key was already used with a different order request."
    )


def test_create_order_requires_idempotency_key() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/orders",
        json={
            "external_order_id": "OMS-1005",
            "warehouse_id": "WH-01",
            "lines": [{"sku": "SKU-WHITE-SHOES", "quantity": 1}],
        },
    )

    assert response.status_code == 422


def test_create_order_rejects_invalid_quantity() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-invalid-quantity"},
        json={
            "external_order_id": "OMS-1006",
            "warehouse_id": "WH-01",
            "lines": [{"sku": "SKU-WHITE-SHOES", "quantity": 0}],
        },
    )

    assert response.status_code == 422


def test_create_order_allocates_inventory() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-allocate"},
        json={
            "external_order_id": "OMS-1008",
            "warehouse_id": "WH-01",
            "lines": [{"sku": "SKU-RED-SHIRT", "quantity": 2}],
        },
    )
    inventory_response = client.get("/inventory", params={"warehouse_id": "WH-01"})

    assert response.status_code == 201
    red_shirt = _find_inventory_item(
        inventory_response.json(),
        warehouse_id="WH-01",
        sku="SKU-RED-SHIRT",
    )
    assert red_shirt["on_hand_quantity"] == 10
    assert red_shirt["allocated_quantity"] == 2
    assert red_shirt["available_quantity"] == 8


def test_create_order_rejects_unknown_warehouse() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-unknown-warehouse"},
        json={
            "external_order_id": "OMS-1009",
            "warehouse_id": "WH-UNKNOWN",
            "lines": [{"sku": "SKU-RED-SHIRT", "quantity": 1}],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown warehouse: WH-UNKNOWN."


def test_create_order_rejects_unknown_sku() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-unknown-sku"},
        json={
            "external_order_id": "OMS-1010",
            "warehouse_id": "WH-01",
            "lines": [{"sku": "SKU-UNKNOWN", "quantity": 1}],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown SKU: SKU-UNKNOWN."


def test_create_order_rejects_sku_not_stocked_at_warehouse() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-not-stocked"},
        json={
            "external_order_id": "OMS-1011",
            "warehouse_id": "WH-02",
            "lines": [{"sku": "SKU-BLUE-HAT", "quantity": 1}],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "SKU SKU-BLUE-HAT is not stocked at warehouse WH-02."


def test_create_order_rejects_insufficient_inventory() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-insufficient-inventory"},
        json={
            "external_order_id": "OMS-1012",
            "warehouse_id": "WH-02",
            "lines": [{"sku": "SKU-RED-SHIRT", "quantity": 5}],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Insufficient inventory for SKU SKU-RED-SHIRT at warehouse WH-02: "
        "requested 5, available 4."
    )


def test_get_unknown_order_returns_not_found() -> None:
    client = TestClient(create_app())

    response = client.get("/orders/unknown-order-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found."


def _find_inventory_item(
    inventory_items: list[dict[str, object]],
    warehouse_id: str,
    sku: str,
) -> dict[str, object]:
    return next(
        item
        for item in inventory_items
        if item["warehouse_id"] == warehouse_id and item["sku"] == sku
    )
