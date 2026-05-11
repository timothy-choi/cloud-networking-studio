"""Deployment lifecycle hardening — validation, duplicates, destroy, redeploy, failures."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.models.topology import NodeType, Topology, TopologyLink, TopologyNode, TopologyStatus
from app.services.deployment_validation import validate_topology_for_deploy

TOPO_BODY = {
    "name": "Lifecycle Lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _topology_two_nodes_linked(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "b",
            "node_type": NodeType.HOST.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": na["id"],
            "target_node_id": nb["id"],
            "network_name": "n0",
            "cidr": "10.5.0.0/24",
            "config": None,
        },
    )
    return tid, na["id"], nb["id"]


def test_duplicate_deploy_rejected_with_409(client):
    tid, _, _ = _topology_two_nodes_linked(client)
    assert client.post(f"/topologies/{tid}/deploy").status_code == 201
    dup = client.post(f"/topologies/{tid}/deploy")
    assert dup.status_code == 409
    assert "active deployment" in dup.json()["detail"].lower()

    did = client.get(f"/topologies/{tid}/runtime").json()["latest_deployment_id"]
    msgs = " ".join(e["message"] for e in client.get(f"/deployments/{did}/events").json())
    assert "Duplicate deployment rejected" in msgs


def test_destroy_idempotent(client):
    tid, _, _ = _topology_two_nodes_linked(client)
    d1 = client.post(f"/topologies/{tid}/deploy").json()
    did = d1["id"]
    assert client.post(f"/deployments/{did}/destroy").status_code == 200
    assert client.post(f"/deployments/{did}/destroy").status_code == 200
    msgs = " ".join(e["message"] for e in client.get(f"/deployments/{did}/events").json())
    assert "already stopped" in msgs
    assert "Destroy idempotent" in msgs


def test_failed_deploy_records_cleanup_events(client, monkeypatch):
    tid, _, _ = _topology_two_nodes_linked(client)
    prov = MagicMock()
    prov.deploy.side_effect = RuntimeError("simulated failure")
    monkeypatch.setattr("app.api.deployments.runtime_provider_for_topology", lambda _rt: prov)

    r = client.post(f"/topologies/{tid}/deploy")
    assert r.status_code == 500

    did = client.get(f"/topologies/{tid}/runtime").json()["latest_deployment_id"]
    dep = client.get(f"/deployments/{did}").json()
    assert dep["status"] == "failed"
    msgs = " ".join(e["message"] for e in dep["events"])
    assert "Partial failure cleanup started" in msgs
    assert "Partial failure cleanup completed" in msgs
    assert "simulated failure" in msgs


def test_redeploy_after_destroy_allowed(client):
    tid, _, _ = _topology_two_nodes_linked(client)
    d1 = client.post(f"/topologies/{tid}/deploy").json()
    did1 = d1["id"]
    assert client.post(f"/deployments/{did1}/destroy").status_code == 200

    d2 = client.post(f"/topologies/{tid}/deploy")
    assert d2.status_code == 201
    body = d2.json()
    did2 = body["id"]
    assert did2 != did1
    assert body["status"] == "succeeded"
    msgs = " ".join(e["message"] for e in body["events"])
    assert "Redeploy allowed after stopped" in msgs


def test_deploy_no_nodes_returns_400(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    r = client.post(f"/topologies/{tid}/deploy")
    assert r.status_code == 400
    body = r.json()
    assert body["status"] == "failed"
    assert "Topology validation failed" in " ".join(e["message"] for e in body["events"])


def test_multi_node_without_link_returns_400(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    for name in ("x", "y"):
        client.post(
            f"/topologies/{tid}/nodes",
            json={
                "name": name,
                "node_type": NodeType.GENERIC.value,
                "image": None,
                "ip_address": None,
                "config": None,
            },
        )
    r = client.post(f"/topologies/{tid}/deploy")
    assert r.status_code == 400


def test_duplicate_ips_rejected(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    ip = "10.5.0.10"
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": ip,
            "config": None,
        },
    ).json()
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "b",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": ip,
            "config": None,
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": na["id"],
            "target_node_id": nb["id"],
            "network_name": "n0",
            "cidr": "10.5.0.0/24",
            "config": None,
        },
    )
    r = client.post(f"/topologies/{tid}/deploy")
    assert r.status_code == 400
    assert "Duplicate intended" in r.text


def test_ip_outside_subnet_rejected(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": "192.168.50.1",
            "config": None,
        },
    ).json()
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "b",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": "10.5.0.20",
            "config": None,
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": na["id"],
            "target_node_id": nb["id"],
            "network_name": "n0",
            "cidr": "10.5.0.0/24",
            "config": None,
        },
    )
    r = client.post(f"/topologies/{tid}/deploy")
    assert r.status_code == 400
    assert "not within any link subnet" in r.text


def test_validate_topology_missing_link_target():
    tid = uuid.uuid4()
    n1 = uuid.uuid4()
    n2 = uuid.uuid4()
    orphan = uuid.uuid4()
    topo = Topology(
        id=tid,
        name="t",
        description=None,
        status=TopologyStatus.DRAFT,
        runtime_target="docker",
        networking_mode="bridge",
        config=None,
    )
    topo.nodes.append(
        TopologyNode(
            id=n1,
            topology_id=tid,
            name="a",
            node_type=NodeType.GENERIC,
            image=None,
            ip_address=None,
            config=None,
        )
    )
    topo.nodes.append(
        TopologyNode(
            id=n2,
            topology_id=tid,
            name="b",
            node_type=NodeType.GENERIC,
            image=None,
            ip_address=None,
            config=None,
        )
    )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=n1,
            target_node_id=orphan,
            network_name="n",
            cidr="10.0.0.0/24",
            config=None,
        )
    )
    errs = validate_topology_for_deploy(topo)
    assert any("missing target node" in e.lower() for e in errs)


def test_lifecycle_status_sequence_on_success(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "solo",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    body = client.post(f"/topologies/{tid}/deploy").json()
    assert body["status"] == "succeeded"
    assert body["started_at"] is not None
    assert body["finished_at"] is not None
