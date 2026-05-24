"""Rollback impact detection and modes."""

from __future__ import annotations

import uuid
from uuid import UUID

from app.db.session import SessionLocal
from app.models.deployment import (
    Deployment,
    DeploymentCleanupStatus,
    DeploymentStatus,
    TopologySyncStatus,
)
from app.models.topology import NodeType
from app.providers.docker_runtime_provider import fake_remaining_containers

TOPO_BODY = {
    "name": "Rollback Lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _register(client_strict, prefix: str = "rb") -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "R"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _client_server_topology(client, headers) -> tuple[str, dict]:
    """Topology with client+server nodes and an empty baseline version."""
    tid = client.post("/topologies", headers=headers, json=TOPO_BODY).json()["id"]
    v_empty = client.post(
        f"/topologies/{tid}/versions", headers=headers, json={"name": "empty"}
    ).json()
    client_node = client.post(
        f"/topologies/{tid}/nodes",
        headers=headers,
        json={
            "name": "client",
            "node_type": NodeType.GENERIC.value,
            "image": "nginx:latest",
        },
    ).json()
    server_node = client.post(
        f"/topologies/{tid}/nodes",
        headers=headers,
        json={
            "name": "server",
            "node_type": NodeType.HOST.value,
            "image": "nginx:latest",
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        headers=headers,
        json={
            "source_node_id": client_node["id"],
            "target_node_id": server_node["id"],
            "network_name": "net0",
            "cidr": "10.9.0.0/24",
        },
    )
    return tid, v_empty


def _empty_version_then_populated(client, headers) -> tuple[str, dict]:
    tid = client.post("/topologies", headers=headers, json=TOPO_BODY).json()["id"]
    v_empty = client.post(
        f"/topologies/{tid}/versions", headers=headers, json={"name": "empty"}
    ).json()
    na = client.post(
        f"/topologies/{tid}/nodes",
        headers=headers,
        json={"name": "a", "node_type": NodeType.GENERIC.value, "image": "nginx:latest"},
    ).json()
    nb = client.post(
        f"/topologies/{tid}/nodes",
        headers=headers,
        json={"name": "b", "node_type": NodeType.HOST.value, "image": "nginx:latest"},
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        headers=headers,
        json={
            "source_node_id": na["id"],
            "target_node_id": nb["id"],
            "network_name": "net0",
            "cidr": "10.9.0.0/24",
        },
    )
    return tid, v_empty


def _deploy(client, headers, tid: str) -> str:
    dep = client.post(f"/topologies/{tid}/deploy", headers=headers)
    assert dep.status_code == 201, dep.text
    return dep.json()["id"]


def _load_deployment(dep_id: str) -> Deployment:
    with SessionLocal() as db:
        dep = db.get(Deployment, UUID(dep_id))
        assert dep is not None
        db.expunge(dep)
        return dep


def test_rollback_with_no_active_deployments(client_strict):
    h = _register(client_strict)
    tid, _ = _empty_version_then_populated(client_strict, h)
    v = client_strict.post(f"/topologies/{tid}/versions", headers=h, json={"name": "snap"}).json()
    rb = client_strict.post(f"/topologies/{tid}/versions/{v['id']}/rollback", headers=h, json={"mode": "config_only"})
    assert rb.status_code == 200, rb.text
    assert rb.json()["mode"] == "config_only"
    assert rb.json()["impact"]["active_deployment_count"] == 0


def test_rollback_impact_detects_active_deployments(client_strict):
    h = _register(client_strict)
    tid, v_empty = _empty_version_then_populated(client_strict, h)
    _deploy(client_strict, h, tid)
    impact = client_strict.get(
        f"/topologies/{tid}/versions/{v_empty['id']}/rollback-impact",
        headers=h,
    )
    assert impact.status_code == 200, impact.text
    body = impact.json()
    assert body["active_deployment_count"] == 1
    assert body["removes_deployed_nodes"] is True
    assert body["warning_message"]


def test_rollback_config_only_marks_drifted(client_strict):
    h = _register(client_strict)
    tid, v_empty = _empty_version_then_populated(client_strict, h)
    dep_id = _deploy(client_strict, h, tid)

    rb = client_strict.post(
        f"/topologies/{tid}/versions/{v_empty['id']}/rollback",
        headers=h,
        json={"mode": "config_only"},
    )
    assert rb.status_code == 200, rb.text
    assert rb.json()["impact"]["active_deployment_count"] == 1

    nodes = client_strict.get(f"/topologies/{tid}/nodes", headers=h).json()
    assert len(nodes) == 0

    dep = _load_deployment(dep_id)
    assert dep.topology_sync_status == TopologySyncStatus.OUT_OF_SYNC
    assert dep.status == DeploymentStatus.SUCCEEDED

    runtime = client_strict.get(f"/topologies/{tid}/runtime", headers=h).json()
    assert runtime["topology_sync_status"] == "out_of_sync"


def test_rollback_and_destroy_stops_active_deployments(client_strict):
    h = _register(client_strict)
    tid, v_empty = _empty_version_then_populated(client_strict, h)
    dep_id = _deploy(client_strict, h, tid)

    rb = client_strict.post(
        f"/topologies/{tid}/versions/{v_empty['id']}/rollback",
        headers=h,
        json={"mode": "rollback_and_destroy"},
    )
    assert rb.status_code == 200, rb.text
    assert dep_id in [str(x) for x in rb.json()["destroyed_deployment_ids"]]

    dep = _load_deployment(dep_id)
    assert dep.status == DeploymentStatus.STOPPED
    assert dep.cleanup_status == DeploymentCleanupStatus.CLEAN


def test_rollback_and_destroy_removes_all_client_server_containers(client_strict):
    h = _register(client_strict)
    tid, v_empty = _client_server_topology(client_strict, h)
    dep_id = _deploy(client_strict, h, tid)

    assert fake_remaining_containers(UUID(dep_id)) == {"cns-client", "cns-server"}

    rb = client_strict.post(
        f"/topologies/{tid}/versions/{v_empty['id']}/rollback",
        headers=h,
        json={"mode": "rollback_and_destroy"},
    )
    assert rb.status_code == 200, rb.text

    assert fake_remaining_containers(UUID(dep_id)) == set()

    dep = _load_deployment(dep_id)
    assert dep.status == DeploymentStatus.STOPPED
    assert dep.cleanup_status == DeploymentCleanupStatus.CLEAN

    nodes = client_strict.get(f"/topologies/{tid}/nodes", headers=h).json()
    assert len(nodes) == 0


def test_rollback_destroy_runs_before_topology_mutation(client_strict, monkeypatch):
    h = _register(client_strict)
    tid, v_empty = _empty_version_then_populated(client_strict, h)
    _deploy(client_strict, h, tid)

    call_order: list[str] = []

    import app.services.topology_rollback_service as rb_svc
    import app.services.topology_version_service as version_svc

    original_rollback = version_svc.rollback_topology_to_version
    original_destroy = rb_svc.destroy_deployment_record

    def track_destroy(*args, **kwargs):
        call_order.append("destroy")
        return original_destroy(*args, **kwargs)

    def track_rollback(*args, **kwargs):
        call_order.append("rollback")
        return original_rollback(*args, **kwargs)

    monkeypatch.setattr(rb_svc, "destroy_deployment_record", track_destroy)
    monkeypatch.setattr(version_svc, "rollback_topology_to_version", track_rollback)

    rb = client_strict.post(
        f"/topologies/{tid}/versions/{v_empty['id']}/rollback",
        headers=h,
        json={"mode": "rollback_and_destroy"},
    )
    assert rb.status_code == 200, rb.text
    assert call_order == ["destroy", "rollback"]


def test_rollback_and_redeploy_recreates_for_non_empty_topology(client_strict):
    h = _register(client_strict)
    tid, _ = _empty_version_then_populated(client_strict, h)
    v1 = client_strict.post(f"/topologies/{tid}/versions", headers=h, json={"name": "baseline"}).json()
    dep_old = _deploy(client_strict, h, tid)

    client_strict.post(
        f"/topologies/{tid}/nodes",
        headers=h,
        json={"name": "extra", "node_type": NodeType.HOST.value, "image": "nginx:latest"},
    )

    rb = client_strict.post(
        f"/topologies/{tid}/versions/{v1['id']}/rollback",
        headers=h,
        json={"mode": "rollback_and_redeploy"},
    )
    assert rb.status_code == 200, rb.text
    assert str(dep_old) in [str(x) for x in rb.json()["destroyed_deployment_ids"]]
    assert rb.json()["redeployed_deployment_id"] is not None

    old = _load_deployment(dep_old)
    assert old.status == DeploymentStatus.STOPPED

    new = _load_deployment(rb.json()["redeployed_deployment_id"])
    assert new.status in (
        DeploymentStatus.SUCCEEDED,
        DeploymentStatus.DEPLOYING,
        DeploymentStatus.PENDING,
    )
    assert new.topology_sync_status == TopologySyncStatus.IN_SYNC


def test_rollback_to_empty_skips_redeploy(client_strict):
    h = _register(client_strict)
    tid, v_empty = _empty_version_then_populated(client_strict, h)
    _deploy(client_strict, h, tid)

    rb = client_strict.post(
        f"/topologies/{tid}/versions/{v_empty['id']}/rollback",
        headers=h,
        json={"mode": "rollback_and_redeploy"},
    )
    assert rb.status_code == 200, rb.text
    assert rb.json()["redeployed_deployment_id"] is None
    assert "empty" in rb.json()["message"].lower() or "skipped" in rb.json()["message"].lower()
