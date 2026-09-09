# WMS Order Lifecycle Simulator

![WMS operator console](stock_images/order-lifecycle.png)

A small, runnable Warehouse Management System (WMS) simulator for learning how an order moves from an Order Management System (OMS) into warehouse execution and back as a shipment confirmation.

It combines a FastAPI REST API, persistent PostgreSQL storage, Alembic migrations, Docker Compose, and a focused operator console. The result is an environment you can run locally, test end to end, and explain clearly in an integration or WMS interview.

## Why This Repository Exists

Warehouse software sits at the point where digital orders become physical work. An OMS knows what a customer bought; a WMS decides whether stock can be allocated, creates work for the warehouse, records what was actually picked, and confirms what finally shipped.

That boundary creates useful engineering problems that are easy to describe but much better to demonstrate:

- inventory can be available, allocated, picked, cancelled, or consumed
- warehouse execution can discover a short pick after allocation
- duplicate requests must not allocate stock twice
- downstream shipment confirmations can fail, retry, or enter a dead-letter queue
- one correlation ID should make a lifecycle traceable across services
- state must survive an application restart

This project keeps the domain intentionally small. It is not a commercial WMS replacement; it is a compact learning and demonstration system for order orchestration, inventory control, fulfillment state, persistence, and integration reliability.

## What A WMS Does

A WMS manages the execution of physical warehouse operations. A typical flow includes receiving inventory, storing it, allocating stock to demand, creating pick work, recording picked quantities, packing cartons, shipping units, and sending the result to connected systems.

The OMS-to-WMS distinction in this simulator is:

```text
OMS: customer order and demand
  -> middleware/API: validation and message handoff
  -> WMS: allocation, picking, packing, and shipping
  -> middleware/API: shipment confirmation
  -> OMS: fulfillment result
```

The project models the most useful slice of that flow without introducing a queue broker, carrier integration, or warehouse hardware.

## What This Project Covers

The simulator focuses on the journey of an order through a warehouse fulfillment flow:

```text
OMS -> Middleware -> WMS -> Warehouse Execution -> WMS -> Middleware -> OMS
```

The WMS simulator is designed to:

- Receive customer orders through a REST API
- Validate SKU, warehouse, and requested quantity
- Store order and inventory records
- Allocate inventory to orders
- Create simulated warehouse pick tasks
- Handle short-pick scenarios
- Pack and ship orders
- Publish shipment confirmations
- Retry transient integration failures
- Prevent duplicate processing with idempotency
- Send unrecoverable messages to a mock dead-letter queue
- Use logs and correlation IDs for troubleshooting

## Tech Stack

- Python 3.11+
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Pydantic
- pytest
- Structured logging with correlation IDs

## Console Views

The browser console at `/` is the primary demo surface. It shows the persisted operational queues and keeps the latest API response visible for endpoint-level learning.

| Orders | Inventory |
| --- | --- |
| ![Orders queue](stock_images/orders.png) | ![Inventory view](stock_images/inventory.png) |

| Picks | Integration |
| --- | --- |
| ![Pick queue](stock_images/picks.png) | ![Integration queue](stock_images/integrations.png) |

## Order Lifecycle States

```text
RECEIVED
VALIDATED
ALLOCATED
PICKING
PICKED
SHORT_PICK
SHORT_PICK_RESOLVED
CANCELLED
PACKED
SHIPPED
CONFIRMATION_PUBLISHED
FAILED
```

## Example Scenarios

- Successful order fulfillment
- Duplicate order request
- Insufficient inventory
- Short pick during warehouse execution
- Temporary shipment confirmation failure followed by retry
- Permanent integration failure routed to a dead-letter queue

## Project Status

This project is being built in achievable milestones. The core lifecycle, reliability simulation, observability, demo scripts, and database-backed repository layer are implemented.

Completed so far:

- FastAPI project skeleton
- `/health` endpoint
- Basic pytest setup
- Order creation endpoint
- Order retrieval endpoint
- Idempotency key handling for duplicate order requests
- Correlation ID capture for order intake
- Seeded inventory endpoint
- SKU, warehouse, and quantity validation during order intake
- Inventory allocation for accepted orders
- Warehouse pick task creation after order allocation
- Pick task listing and retrieval
- Full-pick and short-pick completion
- Pack endpoint for picked orders
- Ship endpoint for packed orders
- Shipment records
- Pending shipment confirmation messages
- Shipment confirmation publishing simulation
- Transient failure retry scheduling
- Permanent failure routing to a mock dead-letter queue
- Correlation ID response headers
- Structured JSON lifecycle logs
- Swagger/OpenAPI request examples
- Repeatable demo scripts
- SQLAlchemy database models and repositories
- Alembic initial schema migration
- Docker Compose PostgreSQL service
- Persistence regression test across app instances
- Short-pick resolution with the `CANCEL_REMAINDER` policy
- Persisted order list endpoint
- Operator console at `/` for lifecycle demos and endpoint testing
- Docker Compose API service with migration-before-start

Current storage note:

- Orders, inventory, pick tasks, shipments, integration messages, and dead-letter records now use SQLAlchemy-backed repositories.
- With no `.env`, the app defaults to in-memory SQLite for quick tests and demos.
- For durable local storage, run the Docker Compose PostgreSQL service and apply the versioned migrations.

## Current API

### Health Check

```http
GET /health
```

The Docker console uses the database readiness check:

```http
GET /health/ready
```

### Create Order

Creates an order, validates inventory, allocates stock, and creates an open warehouse pick task when the request is accepted.

```http
POST /orders
X-Idempotency-Key: idem-order-1001
X-Correlation-ID: corr-order-1001
```

Example body:

```json
{
  "external_order_id": "OMS-1001",
  "warehouse_id": "WH-01",
  "customer_id": "CUST-01",
  "lines": [
    {
      "sku": "SKU-RED-SHIRT",
      "quantity": 2
    }
  ]
}
```

### Get Order

```http
GET /orders/{order_id}
```

### List Orders

```http
GET /orders
```

### List Inventory

```http
GET /inventory
GET /inventory?warehouse_id=WH-01
```

### List Pick Tasks

```http
GET /warehouse/picks
GET /warehouse/picks?order_id={order_id}
```

### Get Pick Task

```http
GET /warehouse/picks/{pick_task_id}
```

### Complete Pick Task

```http
POST /warehouse/picks/{pick_task_id}/complete
```

Example body:

```json
{
  "lines": [
    {
      "order_line_id": "order-line-id-from-pick-task",
      "picked_quantity": 2
    }
  ]
}
```

### Pack Order

```http
POST /orders/{order_id}/pack
```

Packing is allowed after a full pick or after a short pick is resolved with the `CANCEL_REMAINDER` policy.

### Resolve Short Pick

```http
POST /orders/{order_id}/resolve-short-pick
```

Example body:

```json
{
  "policy": "CANCEL_REMAINDER"
}
```

This releases unpicked allocation, records cancelled quantities, and allows the picked remainder to be packed. If no units were picked, the order becomes `CANCELLED`.

### Ship Order

```http
POST /orders/{order_id}/ship
```

Example body:

```json
{
  "carrier": "UPS",
  "tracking_number": "1Z999AA10123456784"
}
```

Shipping creates a pending shipment confirmation message.

### List Shipments

```http
GET /shipments
GET /shipments?order_id={order_id}
```

### Get Shipment

```http
GET /shipments/{shipment_id}
```

### List Integration Messages

```http
GET /integration/messages
```

### Publish Integration Message

```http
POST /integration/messages/{message_id}/publish
```

Example success body:

```json
{
  "downstream_result": "SUCCESS"
}
```

Example transient failure body:

```json
{
  "downstream_result": "TRANSIENT_FAILURE",
  "error_message": "OMS timeout"
}
```

Example permanent failure body:

```json
{
  "downstream_result": "PERMANENT_FAILURE",
  "error_message": "OMS rejected payload"
}
```

### Retry Integration Message

```http
POST /integration/messages/{message_id}/retry
```

Manual retry uses the same body shape as publish.

### List Dead-Letter Queue

```http
GET /integration/dlq
```

## Demo and Architecture Docs

- [Architecture Walkthrough](docs/ARCHITECTURE.md)
- [Demo Scenarios](docs/DEMO_SCENARIOS.md)
- [Development Tracker](docs/DEVELOPMENT_TRACKER.md)

Open the operator console:

```text
http://127.0.0.1:8000/
```

Run the happy-path demo:

```powershell
.\scripts\demo_happy_path.ps1
```

Run the retry/DLQ demo:

```powershell
.\scripts\demo_retry_and_dlq.ps1
```

## Local Development

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run the API:

```powershell
uvicorn app.main:app --reload
```

By default, the app uses in-memory SQLite when no `.env` file is present. Tests stay isolated and fast; the recommended MVP run path below uses Docker Postgres.

Run with local PostgreSQL:

```powershell
docker compose up --build
```

This starts Postgres with a named volume, runs Alembic migrations, and starts the API plus operator console at `http://127.0.0.1:8000/`. Stop the containers with `docker compose down`; the database data remains in the `postgres_data` volume.

For a local Python API process against Docker Postgres, use:

```powershell
$env:WMS_DATABASE_URL = "postgresql+psycopg://wms:wms@localhost:5432/wms_order_lifecycle"
$env:WMS_DATABASE_AUTO_CREATE_TABLES = "false"
docker compose up -d postgres
python -m alembic upgrade head
uvicorn app.main:app --reload
```

The Windows helper runs the same sequence with one command:

```powershell
.\scripts\start.ps1
```

Alembic is the schema source of truth. `WMS_DATABASE_AUTO_CREATE_TABLES=true` remains useful for isolated SQLite tests, while the Docker runtime uses migrations explicitly.

The API returns `X-Correlation-ID` on responses. If a request supplies that header, the same value is echoed back; otherwise the API generates one.

Run tests:

```powershell
python -m pytest
```
