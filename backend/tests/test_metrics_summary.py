"""Tests for GET /metrics/summary (Step 32 observability)."""

from __future__ import annotations

from app.models.topology import NodeType


def test_metrics_summary_returns_expected_schema(client):
    r = client.get("/metrics/summary")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "total_topologies",
        "total_deployments",
        "active_deployments",
        "failed_deployments",
        "total_traffic_tests",
        "failed_traffic_tests",
        "total_failure_injections",
        "failed_failure_injections",
    ):
        assert key in body
        assert isinstance(body[key], int)
        assert body[key] >= 0
    assert "latest_events" in body
    assert isinstance(body["latest_events"], list)
    for ev in body["latest_events"]:
        assert "id" in ev
        assert ev["source"] == "deployment_event"
        assert "topology_id" in ev
        assert "deployment_id" in ev
        assert "level" in ev
        assert "message" in ev
        assert "created_at" in ev


def test_deployment_events_desc_filter_and_metrics_feed(client):
    r = client.post(
        "/topologies",
        json={
            "name": "Event order lab",
            "description": "e",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    assert r.status_code == 201
    tid = r.json()["id"]
    for name, ntype in (("a", NodeType.GENERIC), ("b", NodeType.HOST)):
        nr = client.post(
            f"/topologies/{tid}/nodes",
            json={
                "name": name,
                "node_type": ntype.value,
                "image": None,
                "ip_address": None,
                "config": None,
            },
        )
        assert nr.status_code == 201
    nodes = client.get(f"/topologies/{tid}/nodes").json()
    by = {n["name"]: n["id"] for n in nodes}
    lr = client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": by["a"],
            "target_node_id": by["b"],
            "network_name": "net0",
            "cidr": "10.0.0.0/24",
            "config": None,
        },
    )
    assert lr.status_code == 201
    d = client.post(f"/topologies/{tid}/deploy")
    assert d.status_code == 201
    did = d.json()["id"]

    asc = client.get(f"/deployments/{did}/events?order=asc")
    assert asc.status_code == 200
    asc_list = asc.json()
    times_asc = [e["created_at"] for e in asc_list]
    assert times_asc == sorted(times_asc)

    desc = client.get(f"/deployments/{did}/events?order=desc")
    assert desc.status_code == 200
    desc_list = desc.json()
    times_desc = [e["created_at"] for e in desc_list]
    assert times_desc == sorted(times_desc, reverse=True)

    err_only = client.get(f"/deployments/{did}/events?level=error")
    assert err_only.status_code == 200
    assert all(e["level"] == "error" for e in err_only.json())

    q = client.get(f"/deployments/{did}/events?q=Deployment+pending")
    assert q.status_code == 200
    qlist = q.json()
    assert len(qlist) >= 1
    assert all("pending" in e["message"].lower() for e in qlist)

    m = client.get("/metrics/summary")
    assert m.status_code == 200
    summary = m.json()
    assert summary["total_deployments"] >= 1
    assert len(summary["latest_events"]) >= 1
