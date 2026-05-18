"""Schema bootstrap: ORM metadata must include auth/project/topology DDL."""

from __future__ import annotations

from sqlalchemy import inspect

from app.db.session import Base, engine
from app.db.startup_schema import import_all_orm_modules, verify_core_schema


def test_import_all_orm_modules_registers_users_table():
    """Fails if ``users`` is not on metadata (e.g. partial model imports)."""
    import_all_orm_modules()
    names = {t.name for t in Base.metadata.sorted_tables}
    assert "users" in names
    assert "projects" in names
    assert "topologies" in names
    assert "project_memberships" in names
    assert "deployment_runtime_resources" in names
    assert "deployment_service_exposures" in names
    assert "user_onboarding" in names


def test_verify_core_schema_after_create_all(engine_db):
    """Post-create_all validation used by lifespan and conftest."""
    verify_core_schema(engine)
    insp = inspect(engine)
    assert "users" in insp.get_table_names()
    assert "projects" in insp.get_table_names()
    assert "project_memberships" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("topologies")}
    assert "project_id" in cols
