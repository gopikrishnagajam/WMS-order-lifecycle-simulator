param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

docker compose up -d postgres
$env:WMS_ENVIRONMENT = "local-docker"
$env:WMS_DATABASE_URL = "postgresql+psycopg://wms:wms@localhost:5432/wms_order_lifecycle"
$env:WMS_DATABASE_AUTO_CREATE_TABLES = "false"
python -m alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
