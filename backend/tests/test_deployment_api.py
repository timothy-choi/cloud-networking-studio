"""Deployment simulation API tests."""

from __future__ import annotations

import uuid

from app.models.topology import NodeType

TOPOLOGY_BODY = {
    "name": "Deploy Lab",
    "description": "deployment test",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def test_deploy_creates_deployment_and_events(client):
    r = client.post("/topologies", json=TOPOLOGY_BODY)
    tid = r.json()["id"]

    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "host-a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "service-b",
            "node_type": NodeType.HOST.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    nodes = client.get(f"/topologies/{tid}/nodes").json()
    by_name = {n["name"]: n["id"] for n in nodes}
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": by_name["host-a"],
            "target_node_id": by_name["service-b"],
            "network_name": "net0",
            "cidr": "10.0.0.0/24",
            "config": None,
        },
    )

    d = client.post(f"/topologies/{tid}/deploy")
    assert d.status_code == 201
    body = d.json()
    assert body["topology_id"] == tid
    assert body["status"] == "succeeded"
    assert body["id"]
    assert len(body["events"]) > 0

    did = body["id"]

    g = client.get(f"/deployments/{did}")
    assert g.status_code == 200
    assert g.json()["id"] == did
    assert len(g.json()["events"]) == len(body["events"])

    ev = client.get(f"/deployments/{did}/events")
    assert ev.status_code == 200
    evlist = ev.json()
    assert len(evlist) == len(body["events"])
    times = [e["created_at"] for e in evlist]
    assert times == sorted(times)

    text = " ".join(e["message"] for e in evlist)
    assert "Deployment pending" in text
    assert "Topology validation passed" in text
    assert "Deployment deploying" in text
    assert "Node container creation scheduled: host-a" in text
    assert "Node container creation scheduled: service-b" in text
    assert "Link scheduled: host-a -> service-b (net0)" in text


def test_deploy_unknown_topology_404(client):
    missing = uuid.uuid4()
    r = client.post(f"/topologies/{missing}/deploy")
    assert r.status_code == 404
