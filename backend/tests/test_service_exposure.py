"""Service exposure API (Step 40)."""

from __future__ import annotations

import uuid
from uuid import UUID

from app.db.session import SessionLocal
from app.models.topology import NodeType
from app.services.deployment_runtime_resource_service import (
    replace_runtime_resources_from_payload,
)


def _reg(client_strict, prefix: str) -> tuple[str, dict[str, str]]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _topology_with_persisted_service(client_strict):
    """Owner + viewer on same project; one fake service runtime row for exposure."""
    _, ha = _reg(client_strict, "eo")
    eb, hb = _reg(client_strict, "ev")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    inv = client_strict.post(
        f"/projects/{pid}/members/invite",
        headers=ha,
        json={"email": eb, "role": "viewer"},
    )
    assert inv.status_code == 201, inv.text

    tid = client_strict.post(
        "/topologies",
        headers=ha,
        json={
            "name": "Expose lab",
            "project_id": pid,
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).json()["id"]
    nid = client_strict.post(
        f"/topologies/{tid}/nodes",
        headers=ha,
        json={
            "name": "api",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()["id"]
    did = client_strict.post(f"/topologies/{tid}/deploy", headers=ha).json()["id"]

    with SessionLocal() as db:
        replace_runtime_resources_from_payload(
            db,
            UUID(did),
            {
                "runtime_provider": "docker",
                "namespace_or_network": "cns-net",
                "resources": [
                    {
                        "type": "service",
                        "service_id": nid,
                        "name": "api",
                        "runtime_name": "cns-node-api",
                        "status": "running",
                        "internal_url": "http://cns-node-api:80",
                        "namespace_or_network": "cns-net",
                        "metadata": {"container_id": "deadbeef"},
                    },
                ],
            },
        )
        db.commit()

    svcs = client_strict.get(f"/deployments/{did}/runtime/services", headers=ha).json()["services"]
    assert len(svcs) == 1
    svc_row_id = svcs[0]["id"]
    topo_service_uuid = svcs[0]["service_id"]
    return ha, hb, did, svc_row_id, topo_service_uuid


def test_expose_list_unexpose_happy_path(client_strict):
    ha, hb, did, svc_row_id, _ = _topology_with_persisted_service(client_strict)
    assert client_strict.get(f"/deployments/{did}/runtime/exposures", headers=ha).json()["exposures"] == []

    exp = client_strict.post(
        f"/deployments/{did}/runtime/services/{svc_row_id}/expose",
        headers=ha,
        json={"ttl_hours": 24},
    )
    assert exp.status_code == 201, exp.text
    body = exp.json()
    assert body["status"] == "active"
    assert body["runtime_resource_id"] == svc_row_id
    assert body["metadata"]["manual_port_forward_required"] is True

    r1 = client_strict.get(f"/deployments/{did}/runtime/exposures", headers=ha)
    assert len(r1.json()["exposures"]) == 1

    assert (
        client_strict.delete(
            f"/deployments/{did}/runtime/services/{svc_row_id}/expose",
            headers=ha,
        ).status_code
        == 204
    )

    r2 = client_strict.get(f"/deployments/{did}/runtime/exposures", headers=ha)
    assert r2.json()["exposures"][0]["status"] == "removed"


def test_viewer_can_list_exposures_but_not_mutate(client_strict):
    ha, hb, did, svc_row_id, _ = _topology_with_persisted_service(client_strict)
    assert client_strict.get(f"/deployments/{did}/runtime/exposures", headers=hb).status_code == 200
    assert (
        client_strict.post(
            f"/deployments/{did}/runtime/services/{svc_row_id}/expose",
            headers=hb,
            json={},
        ).status_code
        == 403
    )
    assert (
        client_strict.delete(
            f"/deployments/{did}/runtime/services/{svc_row_id}/expose",
            headers=hb,
        ).status_code
        == 403
    )


def test_expose_by_topology_service_uuid(client_strict):
    ha, hb, did, _, topo_sid = _topology_with_persisted_service(client_strict)
    r = client_strict.post(
        f"/deployments/{did}/runtime/services/{topo_sid}/expose",
        headers=ha,
        json={},
    )
    assert r.status_code == 201


def test_duplicate_expose_conflict(client_strict):
    ha, hb, did, svc_row_id, _ = _topology_with_persisted_service(client_strict)
    assert (
        client_strict.post(
            f"/deployments/{did}/runtime/services/{svc_row_id}/expose",
            headers=ha,
            json={},
        ).status_code
        == 201
    )
    assert (
        client_strict.post(
            f"/deployments/{did}/runtime/services/{svc_row_id}/expose",
            headers=ha,
            json={},
        ).status_code
        == 409
    )


def test_runtime_payload_includes_exposures_and_instructions(client_strict):
    ha, hb, did, svc_row_id, _ = _topology_with_persisted_service(client_strict)
    client_strict.post(
        f"/deployments/{did}/runtime/services/{svc_row_id}/expose",
        headers=ha,
        json={},
    )
    rt = client_strict.get(f"/deployments/{did}/runtime", headers=ha).json()
    assert len(rt["exposures"]) >= 1
    assert "exposed_services" in rt["instructions"]
