# Development Tracker

This file tracks session-by-session progress so the project can be developed in achievable milestones.

## Current Milestone

Milestone 10: MVP Operator Console

Status: Complete

Goal:

Move the simulator from process-memory repositories to a database-backed repository layer while keeping the API behavior stable.

Scope:

- SQLAlchemy dependencies
- Alembic migration setup
- Database models for current domain objects
- Request-scoped database sessions
- SQLAlchemy-backed repositories
- PostgreSQL local development configuration
- Persistence regression test

## Completed

- Created public project overview in `README.md`
- Created private project guide in `PROJECT_PRIVATE.md`
- Selected Python/FastAPI as the implementation stack
- Created FastAPI application structure
- Added `/health` endpoint
- Added `pyproject.toml` with application and development dependencies
- Created local `.venv`
- Added pytest setup and a health endpoint test
- Added order domain models and schemas
- Added in-memory order repository
- Added order routes
- Added idempotency replay behavior
- Added idempotency conflict behavior
- Added correlation ID handling
- Added order API tests
- Added inventory domain models and schemas
- Added seeded in-memory inventory repository
- Added `GET /inventory`
- Added inventory validation to `POST /orders`
- Added inventory allocation to accepted orders
- Updated accepted orders to return `ALLOCATED`
- Added tests for allocation and inventory rejection paths
- Added warehouse pick task domain models and schemas
- Added in-memory pick task repository
- Added warehouse service
- Added warehouse routes
- Updated accepted orders to create open pick tasks
- Updated accepted orders to return `PICKING`
- Added full-pick completion flow
- Added short-pick completion flow
- Added pick completion validation and rejection paths
- Added warehouse API tests
- Added fulfillment shipment domain models and schemas
- Added in-memory shipment repository
- Added fulfillment service
- Added pack order endpoint
- Added ship order endpoint
- Added shipment listing and retrieval endpoints
- Added integration message domain models and schemas
- Added in-memory integration message repository
- Added integration message listing endpoint
- Added pending shipment confirmation message creation
- Added fulfillment API tests
- Added retry metadata to integration messages
- Added dead-letter message model
- Added integration processing service
- Added shipment confirmation publish endpoint
- Added manual retry endpoint
- Added mock DLQ endpoint
- Added success publishing flow
- Added transient failure retry scheduling
- Added permanent failure DLQ flow
- Added max-attempt DLQ flow
- Added integration reliability tests
- Added correlation ID context helpers
- Added structured JSON logging setup
- Added request middleware for correlation IDs and request logs
- Added lifecycle logs in order, warehouse, fulfillment, and integration services
- Added Swagger/OpenAPI tags and request examples
- Added observability tests
- Added architecture walkthrough doc
- Added demo scenario doc
- Added happy-path PowerShell demo script
- Added retry/DLQ PowerShell demo script
- Added SQLAlchemy, Alembic, and psycopg dependencies
- Added `.env.example` for local database configuration
- Added Docker Compose PostgreSQL service
- Added SQLAlchemy DB models for current domain tables
- Added DB engine, session factory, and inventory seeding setup
- Added Alembic environment and initial schema migration
- Replaced in-memory repository implementations with SQLAlchemy-backed repositories
- Added request-scoped database dependencies
- Updated FastAPI app startup to initialize database access
- Added persistence regression test across app instances
- Added short-pick resolution using the `CANCEL_REMAINDER` policy
- Added `GET /orders` for persisted order history
- Added browser operator console at `/`
- Added Dockerfile and API service to Docker Compose
- Added migration-before-start Docker runtime

## In Progress

- No active implementation task

## Next

- Optional: add backorder, substitution, or split-shipment shortage policies
- Optional: add a background retry worker for scheduled integration messages

## Testing Log

- 2026-09-08: `.\.venv\Scripts\python -m pytest` -> `1 passed`, with two dependency deprecation warnings from the FastAPI/Starlette test client stack.
- 2026-09-08: Started Uvicorn at `http://127.0.0.1:8000` and verified `GET /health` returns `status: ok`.
- 2026-09-08: `.\.venv\Scripts\python -m pytest` -> `8 passed`, with the same two dependency deprecation warnings from the FastAPI/Starlette test client stack.
- 2026-09-08: Started Uvicorn at `http://127.0.0.1:8000`; verified live `POST /orders`, `GET /orders/{order_id}`, and idempotency replay behavior.
- 2026-09-08: `.\.venv\Scripts\python -m pytest` -> `16 passed`, with the same two dependency deprecation warnings from the FastAPI/Starlette test client stack.
- 2026-09-08: Started Uvicorn at `http://127.0.0.1:8000`; verified live `GET /inventory`, live `POST /orders`, and inventory allocation from available `10` to available `8`.
- 2026-09-08: `.\.venv\Scripts\python -m pytest` -> `25 passed`, with the same two dependency deprecation warnings from the FastAPI/Starlette test client stack.
- 2026-09-08: Started Uvicorn at `http://127.0.0.1:8000`; verified live order creation to `PICKING`, pick task retrieval as `OPEN`, and short-pick completion to `SHORT_PICK`.
- 2026-09-08: `.\.venv\Scripts\python -m pytest` -> `35 passed`, with the same two dependency deprecation warnings from the FastAPI/Starlette test client stack.
- 2026-09-08: Started Uvicorn at `http://127.0.0.1:8000`; verified live order flow `PICKING -> PICKED -> PACKED -> SHIPPED` and pending `SHIPMENT_CONFIRMATION` message creation.
- 2026-09-08: `.\.venv\Scripts\python -m pytest` -> `42 passed`, with the same two dependency deprecation warnings from the FastAPI/Starlette test client stack.
- 2026-09-08: Started Uvicorn at `http://127.0.0.1:8000`; verified live transient failure to `RETRY_SCHEDULED`, manual retry to `PUBLISHED`, order status to `CONFIRMATION_PUBLISHED`, and permanent failure to DLQ.
- 2026-09-08: `.\.venv\Scripts\python -m pytest` -> `47 passed`, with the same two dependency deprecation warnings from the FastAPI/Starlette test client stack.
- 2026-09-08: Started Uvicorn at `http://127.0.0.1:8000`; verified `scripts/demo_happy_path.ps1`, `scripts/demo_retry_and_dlq.ps1`, response `X-Correlation-ID`, and JSON lifecycle logs.
- 2026-09-08: `.\.venv\Scripts\python -m alembic upgrade head` -> initial schema migration applied successfully against the default SQLite test URL.
- 2026-09-08: Started Uvicorn at `http://127.0.0.1:8010`; verified `scripts/demo_happy_path.ps1` and `scripts/demo_retry_and_dlq.ps1` after the repository refactor.
- 2026-09-08: `.\.venv\Scripts\python -m pytest` -> `48 passed`, with the same two dependency deprecation warnings from the FastAPI/Starlette test client stack.
- 2026-09-09: Docker Desktop PostgreSQL container verified healthy; migrated the existing volume through `20260909_0003`.
- 2026-09-09: `WMS_TEST_POSTGRES_URL=postgresql+psycopg://wms:wms@localhost:5432/wms_order_lifecycle .venv\\Scripts\\python -m pytest tests\\test_postgres.py tests\\test_short_pick_resolution.py` -> `24 passed`.
- 2026-09-09: `docker compose config`, `node --check app/web/app.js`, and `docker compose build api` completed successfully.
