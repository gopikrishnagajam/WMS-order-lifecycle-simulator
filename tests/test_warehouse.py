from fastapi.testclient import TestClient

from app.main import create_app


def test_order_creation_creates_open_pick_task() -> None:
    client = TestClient(create_app())
    order = _create_order(client, idempotency_key="idem-pick-open", quantity=2)

    response = client.get(f"/warehouse/picks/{order['pick_task_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["pick_task_id"] == order["pick_task_id"]
    assert body["order_id"] == order["order_id"]
    assert body["warehouse_id"] == "WH-01"
    assert body["status"] == "OPEN"
    assert body["correlation_id"] == "corr-warehouse-test"
    assert body["completed_at"] is None
    assert body["lines"] == [
        {
            "order_line_id": order["lines"][0]["line_id"],
            "sku": "SKU-RED-SHIRT",
            "quantity_to_pick": 2,
            "picked_quantity": 0,
            "short_quantity": 2,
        }
    ]


def test_list_pick_tasks_can_filter_by_order() -> None:
    client = TestClient(create_app())
    first_order = _create_order(client, idempotency_key="idem-pick-list-1", quantity=1)
    _create_order(client, idempotency_key="idem-pick-list-2", quantity=1)

    response = client.get(
        "/warehouse/picks",
        params={"order_id": first_order["order_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["pick_task_id"] == first_order["pick_task_id"]


def test_complete_pick_task_marks_order_picked() -> None:
    client = TestClient(create_app())
    order = _create_order(client, idempotency_key="idem-pick-complete", quantity=2)
    order_line_id = order["lines"][0]["line_id"]

    response = client.post(
        f"/warehouse/picks/{order['pick_task_id']}/complete",
        json={
            "lines": [
                {
                    "order_line_id": order_line_id,
                    "picked_quantity": 2,
                }
            ]
        },
    )
    order_response = client.get(f"/orders/{order['order_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == order["order_id"]
    assert body["order_status"] == "PICKED"
    assert body["pick_task"]["status"] == "COMPLETED"
    assert body["pick_task"]["completed_at"] is not None
    assert body["pick_task"]["lines"][0]["picked_quantity"] == 2
    assert body["pick_task"]["lines"][0]["short_quantity"] == 0
    assert order_response.json()["status"] == "PICKED"
    assert order_response.json()["lines"][0]["picked_quantity"] == 2


def test_complete_pick_task_with_short_pick_marks_order_short_pick() -> None:
    client = TestClient(create_app())
    order = _create_order(client, idempotency_key="idem-short-pick", quantity=2)
    order_line_id = order["lines"][0]["line_id"]

    response = client.post(
        f"/warehouse/picks/{order['pick_task_id']}/complete",
        json={
            "lines": [
                {
                    "order_line_id": order_line_id,
                    "picked_quantity": 1,
                }
            ]
        },
    )
    order_response = client.get(f"/orders/{order['order_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["order_status"] == "SHORT_PICK"
    assert body["pick_task"]["status"] == "SHORT_PICK"
    assert body["pick_task"]["lines"][0]["picked_quantity"] == 1
    assert body["pick_task"]["lines"][0]["short_quantity"] == 1
    assert order_response.json()["status"] == "SHORT_PICK"
    assert order_response.json()["lines"][0]["picked_quantity"] == 1


def test_complete_pick_task_rejects_over_pick() -> None:
    client = TestClient(create_app())
    order = _create_order(client, idempotency_key="idem-over-pick", quantity=2)
    order_line_id = order["lines"][0]["line_id"]

    response = client.post(
        f"/warehouse/picks/{order['pick_task_id']}/complete",
        json={
            "lines": [
                {
                    "order_line_id": order_line_id,
                    "picked_quantity": 3,
                }
            ]
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        f"Picked quantity for order line {order_line_id} cannot exceed "
        "quantity to pick 2."
    )


def test_complete_pick_task_rejects_mismatched_lines() -> None:
    client = TestClient(create_app())
    order = _create_order(client, idempotency_key="idem-mismatch-pick", quantity=2)

    response = client.post(
        f"/warehouse/picks/{order['pick_task_id']}/complete",
        json={
            "lines": [
                {
                    "order_line_id": "unknown-order-line",
                    "picked_quantity": 1,
                }
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Pick completion lines must match the task order lines."
    )


def test_complete_pick_task_rejects_duplicate_lines() -> None:
    client = TestClient(create_app())
    order = _create_order(client, idempotency_key="idem-duplicate-pick", quantity=2)
    order_line_id = order["lines"][0]["line_id"]

    response = client.post(
        f"/warehouse/picks/{order['pick_task_id']}/complete",
        json={
            "lines": [
                {
                    "order_line_id": order_line_id,
                    "picked_quantity": 1,
                },
                {
                    "order_line_id": order_line_id,
                    "picked_quantity": 1,
                },
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        f"Duplicate pick line submitted: {order_line_id}."
    )


def test_complete_pick_task_rejects_already_completed_task() -> None:
    client = TestClient(create_app())
    order = _create_order(client, idempotency_key="idem-already-picked", quantity=2)
    order_line_id = order["lines"][0]["line_id"]
    request_body = {
        "lines": [
            {
                "order_line_id": order_line_id,
                "picked_quantity": 2,
            }
        ]
    }

    client.post(
        f"/warehouse/picks/{order['pick_task_id']}/complete",
        json=request_body,
    )
    response = client.post(
        f"/warehouse/picks/{order['pick_task_id']}/complete",
        json=request_body,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Pick task has already been completed."


def test_complete_unknown_pick_task_returns_not_found() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/warehouse/picks/unknown-pick-task/complete",
        json={
            "lines": [
                {
                    "order_line_id": "line-1",
                    "picked_quantity": 1,
                }
            ]
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Pick task not found."


def _create_order(
    client: TestClient,
    idempotency_key: str,
    quantity: int,
) -> dict[str, object]:
    response = client.post(
        "/orders",
        headers={
            "X-Idempotency-Key": idempotency_key,
            "X-Correlation-ID": "corr-warehouse-test",
        },
        json={
            "external_order_id": idempotency_key.replace("idem", "OMS"),
            "warehouse_id": "WH-01",
            "customer_id": "CUST-WAREHOUSE",
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

