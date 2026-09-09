import logging

from fastapi.testclient import TestClient

from app.main import create_app


def test_response_echoes_supplied_correlation_id() -> None:
    client = TestClient(create_app())

    response = client.get("/health", headers={"X-Correlation-ID": "corr-observe-1"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-observe-1"


def test_response_generates_correlation_id_when_missing() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"]


def test_generated_correlation_id_is_stored_on_order() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/orders",
        headers={"X-Idempotency-Key": "idem-generated-correlation"},
        json={
            "external_order_id": "OMS-GENERATED-CORRELATION",
            "warehouse_id": "WH-01",
            "lines": [
                {
                    "sku": "SKU-RED-SHIRT",
                    "quantity": 1,
                }
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["correlation_id"] == response.headers["X-Correlation-ID"]


def test_request_logs_include_correlation_id(caplog) -> None:
    client = TestClient(create_app())

    with caplog.at_level(logging.INFO):
        response = client.get(
            "/health",
            headers={"X-Correlation-ID": "corr-log-check"},
        )

    assert response.status_code == 200
    assert any(
        getattr(record, "extra_fields", {}).get("event") == "request_completed"
        and getattr(record, "extra_fields", {}).get("correlation_id")
        == "corr-log-check"
        for record in caplog.records
    )


def test_openapi_schema_has_demo_examples() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert {"name": "integration"} in [
        {"name": tag["name"]} for tag in schema["tags"]
    ]
    assert (
        schema["components"]["schemas"]["OrderCreate"]["examples"][0][
            "external_order_id"
        ]
        == "OMS-1001"
    )

