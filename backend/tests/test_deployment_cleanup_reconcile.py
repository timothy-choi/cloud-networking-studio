"""Cleanup reconciles runtime resources with deployment DB state."""

from __future__ import annotations

from app.models.topology import NodeType

TOPO_BODY = {
    "name": "Cleanup Lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _topology_two_nodes_linked(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "client",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "server",
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
            "network_name": "lab-net",
            "cidr": "10.5.0.0/24",
            "config": None,
        },
    )
    return tid, na["id"], nb["id"]


def _deploy_topology(client, tid: str) -> str:
    dep = client.post(f"/topologies/{tid}/deploy")
    assert dep.status_code == 201, dep.text
    return dep.json()["id"]


def test_cleanup_active_deployment_marks_stopped_and_clean(client):
    tid, _, _ = _topology_two_nodes_linked(client)
    did = _deploy_topology(client, tid)

    cleanup = client.post(f"/deployments/{did}/cleanup")
    assert cleanup.status_code == 200, cleanup.text
    body = cleanup.json()
    assert body["ok"] is True
    assert body["cleanup_status"] == "clean"
    assert body["deployment_status"] == "stopped"
    assert body.get("marked_destroyed") is True

    dep_row = client.get(f"/deployments/{did}").json()
    assert dep_row["status"] == "stopped"
    assert dep_row["cleanup_status"] == "clean"

    rt = client.get(f"/topologies/{tid}/runtime")
    assert rt.status_code == 200, rt.text
    runtime = rt.json()
    assert runtime["status"] == "destroyed"
    assert runtime["resources"] == []
    assert "cleaned up" in (runtime.get("message") or "").lower()


def test_topology_runtime_allows_redeploy_after_cleanup(client):
    tid, _, _ = _topology_two_nodes_linked(client)
    did = _deploy_topology(client, tid)
    assert client.post(f"/deployments/{did}/cleanup").status_code == 200

    dup = client.post(f"/topologies/{tid}/deploy")
    assert dup.status_code == 201, dup.text


def test_cleanup_idempotent_when_already_clean(client):
    tid, _, _ = _topology_two_nodes_linked(client)
    did = _deploy_topology(client, tid)
    assert client.post(f"/deployments/{did}/cleanup").status_code == 200
    again = client.post(f"/deployments/{did}/cleanup")
    assert again.status_code == 200
    assert again.json()["cleanup_status"] == "clean"
    assert again.json()["deployment_status"] == "stopped"


def test_traffic_test_fails_gracefully_after_cleanup(client):
    tid, src, tgt = _topology_two_nodes_linked(client)
    did = _deploy_topology(client, tid)
    assert client.post(f"/deployments/{did}/cleanup").status_code == 200

    ping = client.post(
        f"/topologies/{tid}/traffic-tests/ping",
        json={"source_node_id": src, "target_node_id": tgt, "count": 1},
    )
    assert ping.status_code == 201
    body = ping.json()
    assert body["status"] == "failed"
    assert body.get("result") is not None
    assert "no active deployment" in (body["result"].get("stderr") or "").lower()


def test_cleanup_partial_failed_keeps_deployment_active(client, monkeypatch):
    tid, _, _ = _topology_two_nodes_linked(client)
    did = _deploy_topology(client, tid)

    monkeypatch.setattr(
        "app.services.cleanup_service._has_remaining_resources",
        lambda _remaining: True,
    )
    monkeypatch.setattr(
        "app.services.cleanup_service._format_remaining_resources",
        lambda _remaining: "containers=orphan-1",
    )

    cleanup = client.post(f"/deployments/{did}/cleanup")
    assert cleanup.status_code == 200
    body = cleanup.json()
    assert body["partial"] is True
    assert body["cleanup_status"] == "partial_failed"
    assert body["deployment_status"] == "succeeded"

    dep_row = client.get(f"/deployments/{did}").json()
    assert dep_row["status"] == "succeeded"
    assert dep_row["cleanup_status"] == "partial_failed"


def test_cleanup_records_timeline_events(client):
    from app.models.deployment_timeline import TimelineEventType

    tid, _, _ = _topology_two_nodes_linked(client)
    did = _deploy_topology(client, tid)
    assert client.post(f"/deployments/{did}/cleanup").status_code == 200

    timeline = client.get(f"/deployments/{did}/timeline").json()
    events = timeline["events"]
    types = {e["event_type"] for e in events}
    assert TimelineEventType.CLEANUP_REQUESTED.value in types
    assert TimelineEventType.CLEANUP_SUCCEEDED.value in types
    assert TimelineEventType.DEPLOYMENT_MARKED_DESTROYED_AFTER_CLEANUP.value in types
