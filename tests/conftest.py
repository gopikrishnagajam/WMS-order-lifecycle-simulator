"""Keep ordinary tests isolated from the developer's configured database."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Apply before test modules import app.main (which constructs the default app).
os.environ["WMS_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["WMS_DATABASE_AUTO_CREATE_TABLES"] = "true"

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setenv("WMS_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("WMS_DATABASE_AUTO_CREATE_TABLES", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def postgres_database(monkeypatch):
    """Migrate a unique schema; never clear the developer's application tables."""
    database_url = os.environ.get("WMS_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set WMS_TEST_POSTGRES_URL to run PostgreSQL integration tests.")
    schema = "wms_test_" + uuid4().hex
    admin = create_engine(database_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = make_url(database_url).update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("WMS_DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    monkeypatch.setenv("WMS_DATABASE_AUTO_CREATE_TABLES", "false")
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
        yield scoped_url
    finally:
        # schema consists only of the fixed test prefix and a generated UUID.
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
        get_settings.cache_clear()
