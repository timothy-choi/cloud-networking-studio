"""Pytest fixtures — configure DATABASE_URL before any ``app`` imports."""

from __future__ import annotations

import os

_DEFAULT_TEST_DATABASE_URL = (
    # Compose publishes Postgres on host 5433 (see docker-compose.yml). Port 5432 here is
    # usually a local Postgres install → role "cns_user" does not exist.
    # Uses the same DB name as POSTGRES_DB so no extra init is required. Session fixtures
    # run drop_all/create_all — do not run pytest against a DB you need to keep unmodified.
    "postgresql://cns_user:cns_password@127.0.0.1:5433/cloud_networking_studio"
)
# GitHub Actions sets step env DATABASE_URL for the Postgres service; never override that.
if not os.environ.get("GITHUB_ACTIONS"):
    os.environ["DATABASE_URL"] = _DEFAULT_TEST_DATABASE_URL

# Integration tests must never require a local Docker daemon.
os.environ["CNS_USE_FAKE_DOCKER"] = "1"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def engine_db():
    """Recreate schema once per test session for isolation."""
    import app.models  # noqa: F401 — register ORM metadata

    from app.db.session import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(engine_db):
    """HTTP client with startup lifespan (create_all) against the test engine."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
