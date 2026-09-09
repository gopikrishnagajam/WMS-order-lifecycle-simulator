from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "WMS Order Lifecycle Simulator",
        "environment": "local",
    }


def test_readiness_check_confirms_database_access() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
        "environment": "local",
    }
