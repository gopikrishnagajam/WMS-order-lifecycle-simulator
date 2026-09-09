from fastapi.testclient import TestClient

from app.main import create_app


def test_publish_shipment_confirmation_marks_message_and_order_published() -> None:
    client = TestClient(create_app())
    shipped_order = _create_shipped_order(
        client,
        idempotency_key="idem-publish-success",
    )
    message = _get_only_integration_message(client)

    response = client.post(
        f"/integration/messages/{message['message_id']}/publish",
        json={"downstream_result": "SUCCESS"},
    )
    order_response = client.get(f"/orders/{shipped_order['order_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["message"]["status"] == "PUBLISHED"
    assert body["message"]["attempt_count"] == 1
    assert body["message"]["next_retry_at"] is None
    assert body["message"]["last_error"] is None
    assert body["message"]["published_at"] is not None
    assert body["order_status"] == "CONFIRMATION_PUBLISHED"
    assert body["dead_letter"] is None
    assert order_response.json()["status"] == "CONFIRMATION_PUBLISHED"


def test_transient_failure_schedules_retry_without_updating_order() -> None:
    client = TestClient(create_app())
    shipped_order = _create_shipped_order(
        client,
        idempotency_key="idem-transient-failure",
    )
    message = _get_only_integration_message(client)

    response = client.post(
        f"/integration/messages/{message['message_id']}/publish",
        json={
            "downstream_result": "TRANSIENT_FAILURE",
            "error_message": "OMS timeout",
        },
    )
    order_response = client.get(f"/orders/{shipped_order['order_id']}")
    dlq_response = client.get("/integration/dlq")

    assert response.status_code == 200
    body = response.json()
    assert body["message"]["status"] == "RETRY_SCHEDULED"
    assert body["message"]["attempt_count"] == 1
    assert body["message"]["max_attempts"] == 3
    assert body["message"]["next_retry_at"] is not None
    assert body["message"]["last_error"] == "OMS timeout"
    assert body["order_status"] is None
    assert body["dead_letter"] is None
    assert order_response.json()["status"] == "SHIPPED"
    assert dlq_response.json() == []


def test_manual_retry_after_transient_failure_can_publish_message() -> None:
    client = TestClient(create_app())
    shipped_order = _create_shipped_order(
        client,
        idempotency_key="idem-retry-success",
    )
    message = _get_only_integration_message(client)

    client.post(
        f"/integration/messages/{message['message_id']}/publish",
        json={"downstream_result": "TRANSIENT_FAILURE"},
    )
    response = client.post(
        f"/integration/messages/{message['message_id']}/retry",
        json={"downstream_result": "SUCCESS"},
    )
    order_response = client.get(f"/orders/{shipped_order['order_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["message"]["status"] == "PUBLISHED"
    assert body["message"]["attempt_count"] == 2
    assert body["message"]["next_retry_at"] is None
    assert body["message"]["last_error"] is None
    assert body["order_status"] == "CONFIRMATION_PUBLISHED"
    assert order_response.json()["status"] == "CONFIRMATION_PUBLISHED"


def test_permanent_failure_moves_message_to_dlq() -> None:
    client = TestClient(create_app())
    _create_shipped_order(client, idempotency_key="idem-permanent-failure")
    message = _get_only_integration_message(client)

    response = client.post(
        f"/integration/messages/{message['message_id']}/publish",
        json={
            "downstream_result": "PERMANENT_FAILURE",
            "error_message": "OMS rejected payload",
        },
    )
    dlq_response = client.get("/integration/dlq")

    assert response.status_code == 200
    body = response.json()
    assert body["message"]["status"] == "DEAD_LETTERED"
    assert body["message"]["attempt_count"] == 1
    assert body["message"]["last_error"] == "OMS rejected payload"
    assert body["message"]["next_retry_at"] is None
    assert body["order_status"] is None
    assert body["dead_letter"]["original_message_id"] == message["message_id"]
    assert body["dead_letter"]["reason"] == "OMS rejected payload"
    assert body["dead_letter"]["final_attempt_count"] == 1
    assert dlq_response.json()[0]["dead_letter_id"] == (
        body["dead_letter"]["dead_letter_id"]
    )


def test_transient_failure_moves_message_to_dlq_after_max_attempts() -> None:
    client = TestClient(create_app())
    _create_shipped_order(client, idempotency_key="idem-max-attempts")
    message = _get_only_integration_message(client)
    message_id = message["message_id"]

    first_response = client.post(
        f"/integration/messages/{message_id}/publish",
        json={
            "downstream_result": "TRANSIENT_FAILURE",
            "error_message": "OMS timeout 1",
        },
    )
    second_response = client.post(
        f"/integration/messages/{message_id}/retry",
        json={
            "downstream_result": "TRANSIENT_FAILURE",
            "error_message": "OMS timeout 2",
        },
    )
    third_response = client.post(
        f"/integration/messages/{message_id}/retry",
        json={
            "downstream_result": "TRANSIENT_FAILURE",
            "error_message": "OMS timeout 3",
        },
    )

    assert first_response.json()["message"]["status"] == "RETRY_SCHEDULED"
    assert first_response.json()["message"]["attempt_count"] == 1
    assert second_response.json()["message"]["status"] == "RETRY_SCHEDULED"
    assert second_response.json()["message"]["attempt_count"] == 2
    assert third_response.status_code == 200
    body = third_response.json()
    assert body["message"]["status"] == "DEAD_LETTERED"
    assert body["message"]["attempt_count"] == 3
    assert body["message"]["next_retry_at"] is None
    assert body["dead_letter"]["final_attempt_count"] == 3
    assert body["dead_letter"]["reason"] == (
        "Max attempts reached after transient failure: OMS timeout 3"
    )


def test_finalized_message_cannot_be_processed_again() -> None:
    client = TestClient(create_app())
    _create_shipped_order(client, idempotency_key="idem-finalized-message")
    message = _get_only_integration_message(client)

    client.post(
        f"/integration/messages/{message['message_id']}/publish",
        json={"downstream_result": "SUCCESS"},
    )
    response = client.post(
        f"/integration/messages/{message['message_id']}/retry",
        json={"downstream_result": "SUCCESS"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Integration message is already finalized with status PUBLISHED."
    )


def test_publish_unknown_message_returns_not_found() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/integration/messages/unknown-message/publish",
        json={"downstream_result": "SUCCESS"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Integration message not found."


def _create_shipped_order(
    client: TestClient,
    idempotency_key: str,
) -> dict[str, object]:
    order_response = client.post(
        "/orders",
        headers={
            "X-Idempotency-Key": idempotency_key,
            "X-Correlation-ID": "corr-integration-test",
        },
        json={
            "external_order_id": idempotency_key.replace("idem-", "OMS-"),
            "warehouse_id": "WH-01",
            "customer_id": "CUST-INTEGRATION",
            "lines": [
                {
                    "sku": "SKU-RED-SHIRT",
                    "quantity": 1,
                }
            ],
        },
    )
    order = order_response.json()
    pick_response = client.get(f"/warehouse/picks/{order['pick_task_id']}")
    pick_line = pick_response.json()["lines"][0]
    pick_completion_response = client.post(
        f"/warehouse/picks/{order['pick_task_id']}/complete",
        json={
            "lines": [
                {
                    "order_line_id": pick_line["order_line_id"],
                    "picked_quantity": pick_line["quantity_to_pick"],
                }
            ]
        },
    )
    pack_response = client.post(f"/orders/{order['order_id']}/pack")
    ship_response = client.post(
        f"/orders/{order['order_id']}/ship",
        json={
            "carrier": "UPS",
            "tracking_number": f"1Z{idempotency_key.upper()}",
        },
    )

    assert order_response.status_code == 201
    assert pick_completion_response.status_code == 200
    assert pack_response.status_code == 200
    assert ship_response.status_code == 200
    return ship_response.json()["order"]


def _get_only_integration_message(client: TestClient) -> dict[str, object]:
    messages_response = client.get("/integration/messages")

    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 1
    return messages[0]

