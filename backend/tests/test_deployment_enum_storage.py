"""Deployment enum storage — legacy uppercase tolerance and normalization."""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

from app.db.coerced_enum import CoercedStrEnumType, coerce_str_enum
from app.models.deployment import (
    Deployment,
    DeploymentCleanupStatus,
    DeploymentStatus,
    TopologySyncStatus,
)
from app.models.topology import NodeType


class _EnumProbeBase(DeclarativeBase):
    pass


class _DeploymentEnumProbe(_EnumProbeBase):
    __tablename__ = "deployment_enum_probe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[DeploymentStatus] = mapped_column(
        CoercedStrEnumType(DeploymentStatus),
        default=DeploymentStatus.PENDING,
    )
    cleanup_status: Mapped[DeploymentCleanupStatus] = mapped_column(
        CoercedStrEnumType(DeploymentCleanupStatus),
        default=DeploymentCleanupStatus.NONE,
    )
    topology_sync_status: Mapped[TopologySyncStatus] = mapped_column(
        CoercedStrEnumType(TopologySyncStatus),
        default=TopologySyncStatus.IN_SYNC,
    )


def test_coerce_str_enum_accepts_lowercase_values():
    assert coerce_str_enum(DeploymentStatus, "stopped") == DeploymentStatus.STOPPED
    assert coerce_str_enum(DeploymentCleanupStatus, "none") == DeploymentCleanupStatus.NONE


def test_coerce_str_enum_accepts_uppercase_legacy_names():
    assert coerce_str_enum(DeploymentStatus, "STOPPED") == DeploymentStatus.STOPPED
    assert coerce_str_enum(DeploymentStatus, "SUCCEEDED") == DeploymentStatus.SUCCEEDED
    assert coerce_str_enum(DeploymentCleanupStatus, "CLEAN") == DeploymentCleanupStatus.CLEAN
    assert coerce_str_enum(TopologySyncStatus, "OUT_OF_SYNC") == TopologySyncStatus.OUT_OF_SYNC


def test_coerce_str_enum_maps_destroyed_to_stopped():
    assert coerce_str_enum(DeploymentStatus, "destroyed") == DeploymentStatus.STOPPED
    assert coerce_str_enum(DeploymentStatus, "DESTROYED") == DeploymentStatus.STOPPED


def test_coerced_column_loads_uppercase_legacy_status_from_db():
    engine = create_engine("sqlite:///:memory:")
    _EnumProbeBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            _DeploymentEnumProbe(
                id=1,
                status=DeploymentStatus.PENDING,
                cleanup_status=DeploymentCleanupStatus.NONE,
                topology_sync_status=TopologySyncStatus.IN_SYNC,
            )
        )
        session.commit()
        session.connection().execute(
            text(
                """
                UPDATE deployment_enum_probe
                SET status='STOPPED', cleanup_status='NONE', topology_sync_status='OUT_OF_SYNC'
                WHERE id=1
                """
            )
        )
        session.commit()
        row = session.get(_DeploymentEnumProbe, 1)
        assert row is not None
        assert row.status == DeploymentStatus.STOPPED
        assert row.status.value == "stopped"
        assert row.cleanup_status == DeploymentCleanupStatus.NONE
        assert row.topology_sync_status == TopologySyncStatus.OUT_OF_SYNC


def test_coerced_column_persists_lowercase_values():
    engine = create_engine("sqlite:///:memory:")
    _EnumProbeBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            _DeploymentEnumProbe(
                id=1,
                status=DeploymentStatus.SUCCEEDED,
                cleanup_status=DeploymentCleanupStatus.CLEAN,
            )
        )
        session.commit()
        raw = session.connection().execute(
            text("SELECT status, cleanup_status FROM deployment_enum_probe WHERE id=1")
        ).one()
        assert raw[0] == "succeeded"
        assert raw[1] == "clean"


def test_normalize_deployment_status_values_sql():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE deployments (
                    id TEXT PRIMARY KEY,
                    status VARCHAR(32) NOT NULL,
                    cleanup_status VARCHAR(32) NOT NULL DEFAULT 'none',
                    topology_sync_status VARCHAR(32) NOT NULL DEFAULT 'in_sync'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO deployments (id, status, cleanup_status, topology_sync_status) VALUES
                ('1', 'STOPPED', 'NONE', 'OUT_OF_SYNC'),
                ('2', 'succeeded', 'clean', 'in_sync'),
                ('3', 'DESTROYED', 'PARTIAL_FAILED', 'IN_SYNC')
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE deployments
                SET status = CASE
                    WHEN UPPER(TRIM(status)) = 'PENDING' THEN 'pending'
                    WHEN UPPER(TRIM(status)) = 'DEPLOYING' THEN 'deploying'
                    WHEN UPPER(TRIM(status)) = 'SUCCEEDED' THEN 'succeeded'
                    WHEN UPPER(TRIM(status)) = 'FAILED' THEN 'failed'
                    WHEN UPPER(TRIM(status)) = 'STOPPING' THEN 'stopping'
                    WHEN UPPER(TRIM(status)) IN ('STOPPED', 'DESTROYED') THEN 'stopped'
                    WHEN LOWER(TRIM(status)) IN ('stopped', 'destroyed') THEN 'stopped'
                    ELSE LOWER(TRIM(status))
                END
                WHERE status NOT IN (
                    'pending', 'deploying', 'succeeded', 'failed', 'stopping', 'stopped'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE deployments
                SET cleanup_status = CASE
                    WHEN UPPER(TRIM(cleanup_status)) = 'NONE' THEN 'none'
                    WHEN UPPER(TRIM(cleanup_status)) = 'CLEAN' THEN 'clean'
                    WHEN UPPER(TRIM(cleanup_status)) IN ('PARTIAL_FAILED', 'PARTIAL FAILED') THEN 'partial_failed'
                    ELSE LOWER(TRIM(cleanup_status))
                END
                WHERE cleanup_status NOT IN ('none', 'clean', 'partial_failed')
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE deployments
                SET topology_sync_status = CASE
                    WHEN UPPER(TRIM(topology_sync_status)) IN ('OUT_OF_SYNC', 'OUTOFSYNC') THEN 'out_of_sync'
                    WHEN UPPER(TRIM(topology_sync_status)) IN ('IN_SYNC', 'INSYNC') THEN 'in_sync'
                    ELSE LOWER(TRIM(topology_sync_status))
                END
                WHERE topology_sync_status NOT IN ('in_sync', 'out_of_sync')
                """
            )
        )
        rows = conn.execute(
            text(
                "SELECT id, status, cleanup_status, topology_sync_status FROM deployments ORDER BY id"
            )
        ).all()
        assert rows[0][1:] == ("stopped", "none", "out_of_sync")
        assert rows[1][1:] == ("succeeded", "clean", "in_sync")
        assert rows[2][1:] == ("stopped", "partial_failed", "in_sync")


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
        assert dep.status == DeploymentStatus.SUCCEEDED
        assert dep.status.value == "succeeded"
        assert dep.cleanup_status == DeploymentCleanupStatus.NONE

    detail = client.get(f"/deployments/{did}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "succeeded"
    assert detail.json()["cleanup_status"] == "none"


def test_legacy_uppercase_status_loads_after_direct_db_write(client):
    from app.db.session import SessionLocal

    tid = client.post(
        "/topologies",
        json={
            "name": "legacy-status",
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
        db.execute(
            text("UPDATE deployments SET status='STOPPED', cleanup_status='CLEAN' WHERE id=:id"),
            {"id": str(did)},
        )
        db.commit()
        dep = db.get(Deployment, uuid.UUID(did))
        assert dep is not None
        assert dep.status == DeploymentStatus.STOPPED
        assert dep.cleanup_status == DeploymentCleanupStatus.CLEAN

    detail = client.get(f"/deployments/{did}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "stopped"


def test_project_metrics_with_legacy_status_row(client_strict):
    h, pid = _register(client_strict)
    tid = _topology_with_node(client_strict, h)
    did = client_strict.post(f"/topologies/{tid}/deploy", headers=h).json()["id"]

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        db.execute(
            text("UPDATE deployments SET status='STOPPED' WHERE id=:id"),
            {"id": did},
        )
        db.commit()

    r = client_strict.get(f"/projects/{pid}/metrics", headers=h)
    assert r.status_code == 200, r.text
    assert "cleanup_status" in r.json()


def test_topology_runtime_with_legacy_status_row(client):
    tid = client.post(
        "/topologies",
        json={
            "name": "rt-status",
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

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        db.execute(
            text("UPDATE deployments SET status='STOPPED' WHERE id=:id"),
            {"id": did},
        )
        db.commit()

    rt = client.get(f"/topologies/{tid}/runtime")
    assert rt.status_code == 200, rt.text
    assert rt.json()["status"] == "destroyed"


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
