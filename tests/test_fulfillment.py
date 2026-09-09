from fastapi.testclient import TestClient

from app.main import create_app


def test_pack_picked_order_creates_shipment_and_marks_order_packed() -> None:
    client = TestClient(create_app())
    order = _create_picked_order(client, idempotency_key="idem-pack-1001", quantity=2)

    response = client.post(f"/orders/{order['order_id']}/pack")
    order_response = client.get(f"/orders/{order['order_id']}")
    shipments_response = client.get(
        "/shipments",
        params={"order_id": order["order_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["order"]["status"] == "PACKED"
    assert body["order"]["shipment_id"] == body["shipment"]["shipment_id"]
    assert body["shipment"]["status"] == "PACKED"
    assert body["shipment"]["order_id"] == order["order_id"]
    assert body["shipment"]["warehouse_id"] == "WH-01"
    assert body["shipment"]["carrier"] is None
    assert body["shipment"]["tracking_number"] is None
    assert body["shipment"]["shipped_at"] is None
    assert body["shipment"]["lines"] == [
        {
            "order_line_id": order["lines"][0]["line_id"],
            "sku": "SKU-RED-SHIRT",
            "quantity": 2,
        }
    ]
    assert order_response.json()["status"] == "PACKED"
    assert shipments_response.json()[0]["shipment_id"] == body["shipment"]["shipment_id"]


def test_get_shipment_returns_created_shipment() -> None:
    client = TestClient(create_app())
    order = _create_picked_order(client, idempotency_key="idem-get-shipment", quantity=1)
    pack_response = client.post(f"/orders/{order['order_id']}/pack")
    shipment_id = pack_response.json()["shipment"]["shipment_id"]

    response = client.get(f"/shipments/{shipment_id}")

    assert response.status_code == 200
    assert response.json()["shipment_id"] == shipment_id
    assert response.json()["status"] == "PACKED"


def test_ship_packed_order_marks_shipped_and_creates_confirmation_message() -> None:
    client = TestClient(create_app())
    order = _create_picked_order(client, idempotency_key="idem-ship-1001", quantity=2)
    pack_response = client.post(f"/orders/{order['order_id']}/pack")
    shipment_id = pack_response.json()["shipment"]["shipment_id"]

    response = client.post(
        f"/orders/{order['order_id']}/ship",
        json={
            "carrier": "UPS",
            "tracking_number": "1Z999AA10123456784",
        },
    )
    order_response = client.get(f"/orders/{order['order_id']}")
    shipment_response = client.get(f"/shipments/{shipment_id}")
    messages_response = client.get("/integration/messages")

    assert response.status_code == 200
    body = response.json()
    assert body["order"]["status"] == "SHIPPED"
    assert body["shipment"]["status"] == "SHIPPED"
    assert body["shipment"]["carrier"] == "UPS"
    assert body["shipment"]["tracking_number"] == "1Z999AA10123456784"
    assert body["shipment"]["shipped_at"] is not None
    assert body["shipment_confirmation_message"]["status"] == "PENDING"
    assert (
        body["shipment_confirmation_message"]["message_type"]
        == "SHIPMENT_CONFIRMATION"
    )
    assert body["shipment_confirmation_message"]["correlation_id"] == (
        "corr-fulfillment-test"
    )
    assert body["shipment_confirmation_message"]["payload"]["shipment_id"] == shipment_id
    assert body["shipment_confirmation_message"]["payload"]["external_order_id"] == (
        "OMS-ship-1001"
    )
    assert order_response.json()["status"] == "SHIPPED"
    assert shipment_response.json()["status"] == "SHIPPED"
    assert messages_response.json()[0]["message_id"] == (
        body["shipment_confirmation_message"]["message_id"]
    )


def test_ship_order_generates_tracking_number_when_missing() -> None:
    client = TestClient(create_app())
    order = _create_picked_order(
        client,
        idempotency_key="idem-generated-tracking",
        quantity=1,
    )
    client.post(f"/orders/{order['order_id']}/pack")

    response = client.post(
        f"/orders/{order['order_id']}/ship",
        json={"carrier": "SIM_CARRIER"},
    )

    assert response.status_code == 200
    tracking_number = response.json()["shipment"]["tracking_number"]
    assert tracking_number.startswith("TRK-")
    assert len(tracking_number) == 16


def test_pack_rejects_order_that_is_not_picked() -> None:
    client = TestClient(create_app())
    order = _create_order(client, idempotency_key="idem-pack-not-picked", quantity=1)

    response = client.post(f"/orders/{order['order_id']}/pack")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Only PICKED orders can be packed. Current status: PICKING."
    )


def test_pack_rejects_short_pick_order() -> None:
    client = TestClient(create_app())
    order = _create_short_pick_order(
        client,
        idempotency_key="idem-pack-short-pick",
        quantity=2,
        picked_quantity=1,
    )

    response = client.post(f"/orders/{order['order_id']}/pack")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Short-pick orders cannot be packed until the shortage is resolved."
    )


def test_ship_rejects_order_that_is_not_packed() -> None:
    client = TestClient(create_app())
    order = _create_picked_order(
        client,
        idempotency_key="idem-ship-not-packed",
        quantity=1,
    )

    response = client.post(
        f"/orders/{order['order_id']}/ship",
        json={"carrier": "UPS", "tracking_number": "1ZNOTPACKED"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Only PACKED orders can be shipped. Current status: PICKED."
    )


def test_pack_unknown_order_returns_not_found() -> None:
    client = TestClient(create_app())

    response = client.post("/orders/unknown-order/pack")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found."


def test_ship_unknown_order_returns_not_found() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/orders/unknown-order/ship",
        json={"carrier": "UPS", "tracking_number": "1ZUNKNOWN"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found."


def test_get_unknown_shipment_returns_not_found() -> None:
    client = TestClient(create_app())

    response = client.get("/shipments/unknown-shipment")

    assert response.status_code == 404
    assert response.json()["detail"] == "Shipment not found."


def _create_picked_order(
    client: TestClient,
    idempotency_key: str,
    quantity: int,
) -> dict[str, object]:
    order = _create_order(
        client,
        idempotency_key=idempotency_key,
        quantity=quantity,
    )
    pick_response = client.get(f"/warehouse/picks/{order['pick_task_id']}")
    order_line_id = pick_response.json()["lines"][0]["order_line_id"]

    completion_response = client.post(
        f"/warehouse/picks/{order['pick_task_id']}/complete",
        json={
            "lines": [
                {
                    "order_line_id": order_line_id,
                    "picked_quantity": quantity,
                }
            ]
        },
    )

    assert completion_response.status_code == 200
    return client.get(f"/orders/{order['order_id']}").json()


def _create_short_pick_order(
    client: TestClient,
    idempotency_key: str,
    quantity: int,
    picked_quantity: int,
) -> dict[str, object]:
    order = _create_order(
        client,
        idempotency_key=idempotency_key,
        quantity=quantity,
    )
    pick_response = client.get(f"/warehouse/picks/{order['pick_task_id']}")
    order_line_id = pick_response.json()["lines"][0]["order_line_id"]

    completion_response = client.post(
        f"/warehouse/picks/{order['pick_task_id']}/complete",
        json={
            "lines": [
                {
                    "order_line_id": order_line_id,
                    "picked_quantity": picked_quantity,
                }
            ]
        },
    )

    assert completion_response.status_code == 200
    return client.get(f"/orders/{order['order_id']}").json()


def _create_order(
    client: TestClient,
    idempotency_key: str,
    quantity: int,
) -> dict[str, object]:
    response = client.post(
        "/orders",
        headers={
            "X-Idempotency-Key": idempotency_key,
            "X-Correlation-ID": "corr-fulfillment-test",
        },
        json={
            "external_order_id": idempotency_key.replace("idem-", "OMS-"),
            "warehouse_id": "WH-01",
            "customer_id": "CUST-FULFILLMENT",
            "lines": [
                {
                    "sku": "SKU-RED-SHIRT",
                    "quantity": quantity,
                }
            ],
        },
    )

    assert response.status_code == 201
    return response.json()

