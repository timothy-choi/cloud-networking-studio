"""Runtime API integration tests (fake Docker provider — no engine required)."""

from __future__ import annotations

import uuid

from app.models.topology import NodeType


def test_topology_runtime_returns_payload_after_deploy(client):
    r = client.post(
        "/topologies",
        json={
            "name": "Obs Lab",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    tid = r.json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "n1",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    d = client.post(f"/topologies/{tid}/deploy")
    assert d.status_code == 201
    did = d.json()["id"]

    rt = client.get(f"/topologies/{tid}/runtime")
    assert rt.status_code == 200
    body = rt.json()
    assert body["topology_id"] == tid
    assert body["deployment_status"] == "succeeded"
    assert body["latest_deployment_id"] == did
    assert body["networks"] == []
    assert body["containers"] == []
    assert body["runtime_provider"] == "docker"

    ev = client.get(f"/deployments/{did}/events").json()
    assert any("Runtime inspection" in e["message"] for e in ev)

    dr = client.get(f"/deployments/{did}/runtime")
    assert dr.status_code == 200
    dre = dr.json()
    assert dre["deployment_id"] == did
    assert dre["topology_id"] == tid


def test_deployment_reconcile_reports_drift_with_fake_provider(client):
    r = client.post(
        "/topologies",
        json={
            "name": "Reconcile Lab",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    tid = r.json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()["id"]
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "b",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()["id"]
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": na,
            "target_node_id": nb,
            "network_name": "lab-net",
            "cidr": "10.0.0.0/24",
            "config": None,
        },
    )
    dep = client.post(f"/topologies/{tid}/deploy").json()
    did = dep["id"]

    rec = client.post(f"/deployments/{did}/reconcile")
    assert rec.status_code == 200
    payload = rec.json()
    assert payload["missing_network"] is True
    assert uuid.UUID(na) in [uuid.UUID(x) for x in payload["missing_node_ids"]]
    assert uuid.UUID(nb) in [uuid.UUID(x) for x in payload["missing_node_ids"]]

    ev = client.get(f"/deployments/{did}/events").json()
    msgs = [e["message"] for e in ev]
    assert any("Runtime reconciliation started" in m for m in msgs)
    assert any("Missing resource detected" in m for m in msgs)
    assert any("Runtime reconciliation completed" in m for m in msgs)


def test_node_logs_404_without_runtime_container(client):
    r = client.post(
        "/topologies",
        json={
            "name": "Logs",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    tid = r.json()["id"]
    n = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "solo",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    nid = n["id"]
    lg = client.get(f"/nodes/{nid}/logs")
    assert lg.status_code == 404


def test_runtime_topology_unknown_404(client):
    missing = uuid.uuid4()
    assert client.get(f"/topologies/{missing}/runtime").status_code == 404


def test_runtime_deployment_unknown_404(client):
    missing = uuid.uuid4()
    assert client.get(f"/deployments/{missing}/runtime").status_code == 404
