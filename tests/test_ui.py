from fastapi.testclient import TestClient

from app.main import create_app


def test_operator_console_is_served() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "WMS Control Room" in response.text
    assert "/assets/app.js" in response.text


def test_order_list_returns_persisted_orders() -> None:
    with TestClient(create_app()) as client:
        created = client.post(
            "/orders",
            headers={"X-Idempotency-Key": "ui-list-order"},
            json={
                "external_order_id": "OMS-UI-LIST",
                "warehouse_id": "WH-01",
                "lines": [{"sku": "SKU-BLUE-HAT", "quantity": 1}],
            },
        )
        listed = client.get("/orders")

    assert created.status_code == 201
    assert listed.status_code == 200
    assert listed.json()[0]["order_id"] == created.json()["order_id"]
