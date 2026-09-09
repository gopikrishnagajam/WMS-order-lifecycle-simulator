from fastapi.testclient import TestClient

from app.main import create_app


def test_list_inventory_returns_seeded_stock() -> None:
    client = TestClient(create_app())

    response = client.get("/inventory")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 4
    assert {
        "sku": "SKU-RED-SHIRT",
        "warehouse_id": "WH-01",
        "description": "Red shirt",
        "on_hand_quantity": 10,
        "allocated_quantity": 0,
        "available_quantity": 10,
    } in body


def test_list_inventory_can_filter_by_warehouse() -> None:
    client = TestClient(create_app())

    response = client.get("/inventory", params={"warehouse_id": "WH-02"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["warehouse_id"] == "WH-02"
    assert body[0]["sku"] == "SKU-RED-SHIRT"

