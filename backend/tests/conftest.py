"""Pytest fixtures — configure DATABASE_URL before any ``app`` imports."""

from __future__ import annotations

import os

_DEFAULT_TEST_DATABASE_URL = (
    # Compose publishes Postgres on host 5433 (docker-compose.yml or docker-compose.prod.yml).
    # Port 5432 on localhost is often a different Postgres install → role "cns_user" may not exist.
    # Session fixtures run drop_all/create_all — do not run pytest against a DB you need to keep.
    "postgresql://cns_user:cns_password@127.0.0.1:5433/cloud_networking_studio"
)
# GitHub Actions sets step env DATABASE_URL for the Postgres service; never override that.
if not os.environ.get("GITHUB_ACTIONS"):
    os.environ["DATABASE_URL"] = _DEFAULT_TEST_DATABASE_URL

os.environ.setdefault("AUTH_SECRET_KEY", "pytest-secret-key-min-32-characters-long!!")
os.environ.setdefault("AUTH_REQUIRE_LOGIN", "false")

# Integration tests must never require a local Docker daemon.
os.environ["CNS_USE_FAKE_DOCKER"] = "1"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def engine_db():
    """Recreate schema once per test session for isolation."""
    from app.db.session import Base, engine
    from app.db.startup_schema import import_all_orm_modules, verify_core_schema

    import_all_orm_modules()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    verify_core_schema(engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(engine_db):
    """HTTP client with startup lifespan (create_all) against the test engine."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_strict(engine_db, monkeypatch):
    """HTTP client with AUTH_REQUIRE_LOGIN=true (Bearer required for protected routes)."""
    from app.core.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "auth_require_login", True)
    monkeypatch.setattr(settings, "auth_secret_key", "pytest-secret-key-min-32-characters-long!!")

    with TestClient(app) as test_client:
        yield test_client
