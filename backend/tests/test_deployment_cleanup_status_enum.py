"""DeploymentCleanupStatus enum persistence and API resilience."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Enum, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

from app.models.deployment import Deployment, DeploymentCleanupStatus
from app.models.topology import NodeType


class _CleanupEnumBase(DeclarativeBase):
    pass


class _CleanupProbe(_CleanupEnumBase):
    __tablename__ = "cleanup_enum_probe"

    id: Mapped[int] = mapped_column(primary_key=True)
    cleanup_status: Mapped[DeploymentCleanupStatus] = mapped_column(
        Enum(
            DeploymentCleanupStatus,
            native_enum=False,
            length=32,
            values_callable=lambda members: [member.value for member in members],
        ),
        default=DeploymentCleanupStatus.NONE,
    )


def test_cleanup_status_enum_loads_lowercase_db_value():
    engine = create_engine("sqlite:///:memory:")
    _CleanupEnumBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_CleanupProbe(id=1, cleanup_status=DeploymentCleanupStatus.NONE))
        session.commit()
        session.connection().execute(
            text("UPDATE cleanup_enum_probe SET cleanup_status='none' WHERE id=1")
        )
        session.commit()
        row = session.get(_CleanupProbe, 1)
        assert row is not None
        assert row.cleanup_status == DeploymentCleanupStatus.NONE
        assert row.cleanup_status.value == "none"


def test_cleanup_status_enum_loads_uppercase_legacy_value():
    """Simulates staging rows stored as enum member names before normalization."""
    engine = create_engine("sqlite:///:memory:")
    _CleanupEnumBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_CleanupProbe(id=1, cleanup_status=DeploymentCleanupStatus.CLEAN))
        session.commit()
        session.connection().execute(
            text("UPDATE cleanup_enum_probe SET cleanup_status='CLEAN' WHERE id=1")
        )
        session.commit()
        with pytest.raises(LookupError):
            session.get(_CleanupProbe, 1)


def test_normalize_cleanup_status_values_sql():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE deployments (
                    id TEXT PRIMARY KEY,
                    cleanup_status VARCHAR(32) NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO deployments (id, cleanup_status) VALUES "
                "('1', 'NONE'), ('2', 'clean'), ('3', 'PARTIAL_FAILED'), ('4', 'none')"
            )
        )
        conn.execute(
            text(
                """
                UPDATE deployments
                SET cleanup_status = CASE
                    WHEN cleanup_status IS NULL THEN 'none'
                    WHEN UPPER(TRIM(cleanup_status)) = 'NONE' THEN 'none'
                    WHEN UPPER(TRIM(cleanup_status)) = 'CLEAN' THEN 'clean'
                    WHEN UPPER(TRIM(cleanup_status)) IN ('PARTIAL_FAILED', 'PARTIAL FAILED') THEN 'partial_failed'
                    WHEN LOWER(TRIM(cleanup_status)) = 'none' THEN 'none'
                    WHEN LOWER(TRIM(cleanup_status)) = 'clean' THEN 'clean'
                    WHEN LOWER(TRIM(cleanup_status)) = 'partial_failed' THEN 'partial_failed'
                    ELSE 'none'
                END
                WHERE cleanup_status IS NULL
                   OR TRIM(cleanup_status) = ''
                   OR cleanup_status NOT IN ('none', 'clean', 'partial_failed')
                """
            )
        )
        rows = conn.execute(text("SELECT id, cleanup_status FROM deployments ORDER BY id")).all()
        assert [r[1] for r in rows] == ["none", "clean", "partial_failed", "none"]


def test_deployment_with_none_cleanup_status_loads(client):
    from app.db.session import SessionLocal

    tid = client.post(
        "/topologies",
        json={
            "name": "cleanup-enum",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "n1",
            "node_type": NodeType.GENERIC.value,
            "image": "nginx:alpine",
            "config": None,
        },
    )
    did = client.post(f"/topologies/{tid}/deploy").json()["id"]

    with SessionLocal() as db:
        dep = db.get(Deployment, uuid.UUID(did))
        assert dep is not None
        assert dep.cleanup_status == DeploymentCleanupStatus.NONE
        assert dep.cleanup_status.value == "none"

    detail = client.get(f"/deployments/{did}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["cleanup_status"] == "none"


def test_project_metrics_with_cleanup_status_deployment(client_strict):
    h, pid = _register(client_strict)
    tid = _topology_with_node(client_strict, h)
    client_strict.post(f"/topologies/{tid}/deploy", headers=h)
    r = client_strict.get(f"/projects/{pid}/metrics", headers=h)
    assert r.status_code == 200, r.text
    assert "cleanup_status" in r.json()


def test_topology_runtime_with_cleanup_status_deployment(client):
    tid = client.post(
        "/topologies",
        json={
            "name": "rt-cleanup",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "n1",
            "node_type": NodeType.GENERIC.value,
            "image": "nginx:alpine",
            "config": None,
        },
    )
    client.post(f"/topologies/{tid}/deploy")
    rt = client.get(f"/topologies/{tid}/runtime")
    assert rt.status_code == 200, rt.text
    assert rt.json()["topology_id"] == tid


def test_destroy_writes_valid_cleanup_status(client_strict):
    from tests.test_topology_rollback import (
        _deploy,
        _empty_version_then_populated,
        _register,
    )

    h = _register(client_strict, prefix="clnenum")
    tid, v_empty = _empty_version_then_populated(client_strict, h)
    dep_id = _deploy(client_strict, h, tid)
    rb = client_strict.post(
        f"/topologies/{tid}/versions/{v_empty['id']}/rollback",
        headers=h,
        json={"mode": "rollback_and_destroy"},
    )
    assert rb.status_code == 200, rb.text

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        dep = db.get(Deployment, uuid.UUID(dep_id))
        assert dep is not None
        assert dep.cleanup_status in (
            DeploymentCleanupStatus.CLEAN,
            DeploymentCleanupStatus.PARTIAL_FAILED,
        )
        assert dep.cleanup_status.value in ("clean", "partial_failed")


def _register(client_strict, prefix: str = "m"):
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "M"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    return h, pid


def _topology_with_node(client, headers: dict | None = None) -> str:
    h = headers or {}
    tid = client.post(
        "/topologies",
        json={
            "name": "Metrics Lab",
            "description": "metrics test",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
        headers=h,
    ).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "host-a",
            "node_type": NodeType.GENERIC.value,
            "image": "nginx:alpine",
            "config": None,
        },
        headers=h,
    )
    return tid
