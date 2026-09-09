from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.main import create_app


def test_commit_failure_returns_error_and_rolls_back_before_success_response():
    app = create_app()

    class FailingCommitSession(Session):
        def commit(self):
            raise RuntimeError("Simulated commit failure")

    factory = app.state.session_factory
    app.state.session_factory = sessionmaker(bind=app.state.db_engine, class_=FailingCommitSession)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/orders", headers={"X-Idempotency-Key": "commit-failure"}, json={
            "external_order_id": "OMS-COMMIT", "warehouse_id": "WH-01",
            "lines": [{"sku": "SKU-RED-SHIRT", "quantity": 2}],
        })
        assert response.status_code == 500
        app.state.session_factory = factory
        assert client.get("/warehouse/picks").json() == []
        assert all(item["allocated_quantity"] == 0 for item in client.get("/inventory").json())
    app.state.db_engine.dispose()
