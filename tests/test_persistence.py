from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def test_orders_persist_across_app_instances(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "wms_order_lifecycle.db"
    monkeypatch.setenv(
        "WMS_DATABASE_URL",
        f"sqlite+pysqlite:///{database_path.as_posix()}",
    )
    get_settings.cache_clear()
    first_app = None
    second_app = None

    try:
        first_app = create_app()
        first_client = TestClient(first_app)
        create_response = first_client.post(
            "/orders",
            headers={
                "X-Idempotency-Key": "idem-persistence-test",
                "X-Correlation-ID": "corr-persistence-test",
            },
            json={
                "external_order_id": "OMS-PERSISTENCE-1",
                "warehouse_id": "WH-01",
                "customer_id": "CUST-PERSISTENCE",
                "lines": [{"sku": "SKU-RED-SHIRT", "quantity": 1}],
            },
        )
        assert create_response.status_code == 201
        order_id = create_response.json()["order_id"]
        first_app.state.db_engine.dispose()

        second_app = create_app()
        second_client = TestClient(second_app)
        persisted_response = second_client.get(f"/orders/{order_id}")

        assert persisted_response.status_code == 200
        assert persisted_response.json()["order_id"] == order_id
        assert persisted_response.json()["external_order_id"] == "OMS-PERSISTENCE-1"
        assert persisted_response.json()["status"] == "PICKING"
    finally:
        if first_app is not None:
            first_app.state.db_engine.dispose()
        if second_app is not None:
            second_app.state.db_engine.dispose()
        get_settings.cache_clear()
