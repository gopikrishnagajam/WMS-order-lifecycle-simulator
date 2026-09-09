# Architecture Walkthrough

This project is a simplified WMS integration simulator. The main goal is to show how an order moves through fulfillment and how the integration back to an OMS can succeed, retry, or fail into a DLQ.

## System Flow

```text
OMS request
  -> WMS order intake API
  -> inventory validation and allocation
  -> warehouse pick task
  -> pack
  -> ship
  -> shipment confirmation message
  -> simulated OMS publish result
```

## Current Components

- `orders`: accepts OMS order requests, handles idempotency, and tracks order status
- `inventory`: stores seeded SKU/warehouse stock and allocates available quantity
- `warehouse`: creates and completes pick tasks, including short-pick scenarios
- `fulfillment`: packs picked orders, ships packed orders, and creates shipment records
- `integration`: processes shipment confirmation messages with publish, retry, and DLQ behavior
- `core`: configuration, correlation ID context, structured logging, and request middleware

## Current Storage

Repositories are now backed by SQLAlchemy database models:

- orders
- order lines
- inventory
- pick tasks
- pick task lines
- shipments
- shipment lines
- integration messages
- dead-letter messages

Tests default to in-memory SQLite for isolation. The MVP runtime path is Docker Compose: Postgres uses a named volume, the API waits for database health, and Alembic applies migrations before Uvicorn starts.

FastAPI creates a database session per request. The repositories used by one request share that session, so a multi-step operation such as order intake can allocate inventory, create the order, create the pick task, and update order state in one request transaction.

## Order Lifecycle

```text
POST /orders
  -> PICKING

POST /warehouse/picks/{pick_task_id}/complete
  -> PICKED
  -> or SHORT_PICK

POST /orders/{order_id}/resolve-short-pick
  -> SHORT_PICK_RESOLVED
  -> or CANCELLED when nothing was picked

POST /orders/{order_id}/pack
  -> PACKED

POST /orders/{order_id}/ship
  -> SHIPPED

POST /integration/messages/{message_id}/publish
  -> CONFIRMATION_PUBLISHED
```

Short-pick orders pause at `SHORT_PICK`. The MVP supports `CANCEL_REMAINDER`: unpicked allocation is released, cancelled quantities are recorded, and the picked remainder can continue to packing and shipping. A zero-pick order becomes `CANCELLED`.

The operator console at `/` drives this lifecycle and exposes persisted orders, inventory, pick tasks, shipments, integration messages, and the DLQ in one view.

## Integration Reliability

Shipment confirmation messages can be processed with three simulated downstream results:

- `SUCCESS`: marks the message `PUBLISHED` and the order `CONFIRMATION_PUBLISHED`
- `TRANSIENT_FAILURE`: increments `attempt_count` and schedules `next_retry_at`
- `PERMANENT_FAILURE`: moves the message to `DEAD_LETTERED` and creates a DLQ record

Repeated transient failures also move the message to DLQ after `max_attempts`.

## Observability

Every request receives a correlation ID:

- If `X-Correlation-ID` is supplied, the API echoes it back.
- If it is missing, the API generates one and returns it in the response.
- Order intake stores the same correlation ID on the order.
- Lifecycle logs include the active correlation ID.

Logs are structured as JSON so lifecycle events can be searched by `correlation_id`.

## Interview Summary

A concise way to explain the project:

```text
I built a simplified WMS integration simulator in FastAPI. It receives OMS orders, validates and allocates inventory, creates warehouse pick tasks, supports short picks, packs and ships orders, then creates shipment confirmation messages. I also modeled integration reliability with idempotency keys, correlation IDs, transient retries, permanent failures, and DLQ handling.
```
