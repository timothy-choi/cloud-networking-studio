"""API tests for topology graph persistence (integration-style against DATABASE_URL)."""

from __future__ import annotations

import uuid

from app.models.topology import NodeType

TOPOLOGY_BODY = {
    "name": "Lab",
    "description": "test topology",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_topology_crud_flow(client):
    # Create
    r = client.post("/topologies", json=TOPOLOGY_BODY)
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["name"] == TOPOLOGY_BODY["name"]

    # List
    r = client.get("/topologies")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    row = next(x for x in rows if x["id"] == tid)
    assert row.get("node_count") == 0
    assert row.get("link_count") == 0

    # Get one
    r = client.get(f"/topologies/{tid}")
    assert r.status_code == 200
    assert r.json()["id"] == tid
    assert r.json().get("node_count") == 0
    assert r.json().get("link_count") == 0


def test_nodes_and_links_flow(client):
    r = client.post("/topologies", json=TOPOLOGY_BODY)
    tid = r.json()["id"]

    n1 = {
        "name": "node-a",
        "node_type": NodeType.GENERIC.value,
        "image": "nginx:latest",
        "ip_address": "10.0.0.1",
        "config": {
            "resources": {"cpu": "1.5", "memory_mb": "1024", "disk_gb": "10", "replicas": "2"},
            "exposure": "private",
            "stateful": True,
            "required_ports": [8080],
        },
    }
    n2 = {
        "name": "node-b",
        "node_type": NodeType.HOST.value,
        "image": None,
        "ip_address": "10.0.0.2",
        "config": None,
    }

    ra = client.post(f"/topologies/{tid}/nodes", json=n1)
    assert ra.status_code == 201
    id_a = ra.json()["id"]
    assert ra.json()["topology_id"] == tid
    assert ra.json()["config"]["resources"]["cpu"] == 1.5
    assert ra.json()["config"]["resources"]["memory_mb"] == 1024
    assert ra.json()["config"]["resources"]["disk_gb"] == 10.0
    assert ra.json()["config"]["resources"]["replicas"] == 2
    assert ra.json()["config"]["exposure"] == "private"
    assert ra.json()["config"]["stateful"] is True

    rb = client.post(f"/topologies/{tid}/nodes", json=n2)
    assert rb.status_code == 201
    id_b = rb.json()["id"]

    lr = client.get(f"/topologies/{tid}/nodes")
    assert lr.status_code == 200
    nodes = lr.json()
    assert len(nodes) == 2
    names = {n["name"] for n in nodes}
    assert names == {"node-a", "node-b"}
    node_a = next(n for n in nodes if n["id"] == id_a)
    assert node_a["config"]["resources"]["cpu"] == 1.5

    link_body = {
        "source_node_id": id_a,
        "target_node_id": id_b,
        "network_name": "net0",
        "cidr": "10.0.0.0/24",
        "config": {"mtu": 1500},
    }
    rl = client.post(f"/topologies/{tid}/links", json=link_body)
    assert rl.status_code == 201
    lj = rl.json()
    assert lj["topology_id"] == tid
    assert lj["source_node_id"] == id_a
    assert lj["target_node_id"] == id_b

    ll = client.get(f"/topologies/{tid}/links")
    assert ll.status_code == 200
    links = ll.json()
    assert len(links) == 1
    assert links[0]["network_name"] == "net0"


def test_create_node_unknown_topology_returns_404(client):
    missing = uuid.uuid4()
    r = client.post(
        f"/topologies/{missing}/nodes",
        json={
            "name": "orphan",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    assert r.status_code == 404


def test_link_wrong_topology_returns_404(client):
    """Nodes from topology B cannot be linked under topology A path."""
    ra = client.post("/topologies", json={**TOPOLOGY_BODY, "name": "A"})
    rb = client.post("/topologies", json={**TOPOLOGY_BODY, "name": "B"})
    id_a = ra.json()["id"]
    id_b = rb.json()["id"]

    na = client.post(
        f"/topologies/{id_b}/nodes",
        json={
            "name": "on-b",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    nid = na.json()["id"]

    # Same node twice would be invalid graphically but DB allows — use two nodes on B
    nb = client.post(
        f"/topologies/{id_b}/nodes",
        json={
            "name": "on-b-2",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    nid2 = nb.json()["id"]

    r = client.post(
        f"/topologies/{id_a}/links",
        json={
            "source_node_id": nid,
            "target_node_id": nid2,
            "network_name": "x",
            "cidr": None,
            "config": None,
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Node not found"


def test_patch_delete_nodes_and_links(client):
    r = client.post("/topologies", json=TOPOLOGY_BODY)
    tid = r.json()["id"]

    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": {"editor_position": {"x": 10, "y": 20}},
        },
    )
    assert na.status_code == 201
    id_a = na.json()["id"]

    pu = client.patch(
        f"/topologies/{tid}/nodes/{id_a}",
        json={"name": "a-renamed", "config": {"editor_position": {"x": 50, "y": 60}}},
    )
    assert pu.status_code == 200
    assert pu.json()["name"] == "a-renamed"
    assert pu.json()["config"]["editor_position"]["x"] == 50

    pu_resources = client.patch(
        f"/topologies/{tid}/nodes/{id_a}",
        json={
            "config": {
                "resources": {"cpu": 2, "memory_mb": 2048, "disk_gb": 20, "replicas": 1},
                "exposure": "public",
                "required_ports": [80, 443],
            }
        },
    )
    assert pu_resources.status_code == 200
    assert pu_resources.json()["config"]["resources"]["cpu"] == 2.0
    assert pu_resources.json()["config"]["resources"]["memory_mb"] == 2048
    assert pu_resources.json()["config"]["resources"]["disk_gb"] == 20.0
    assert pu_resources.json()["config"]["exposure"] == "public"
    assert pu_resources.json()["config"]["required_ports"] == [80, 443]

    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "b",
            "node_type": NodeType.HOST.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    id_b = nb.json()["id"]

    lk = client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": id_a,
            "target_node_id": id_b,
            "network_name": "n1",
            "cidr": "10.1.0.0/24",
            "config": None,
        },
    )
    lid = lk.json()["id"]

    pl = client.patch(
        f"/topologies/{tid}/links/{lid}",
        json={"network_name": "n1-renamed", "cidr": "10.2.0.0/24"},
    )
    assert pl.status_code == 200
    assert pl.json()["network_name"] == "n1-renamed"

    dl = client.delete(f"/topologies/{tid}/links/{lid}")
    assert dl.status_code == 204

    dn = client.delete(f"/topologies/{tid}/nodes/{id_a}")
    assert dn.status_code == 204

    nodes = client.get(f"/topologies/{tid}/nodes").json()
    assert len(nodes) == 1
    assert nodes[0]["id"] == id_b


def test_patch_topology_metadata(client):
    r = client.post("/topologies", json=TOPOLOGY_BODY)
    tid = r.json()["id"]
    pr = client.patch(f"/topologies/{tid}", json={"name": "Renamed", "description": "x"})
    assert pr.status_code == 200
    assert pr.json()["name"] == "Renamed"
    assert pr.json()["description"] == "x"


def test_delete_topology(client):
    r = client.post("/topologies", json=TOPOLOGY_BODY)
    tid = r.json()["id"]
    assert client.delete(f"/topologies/{tid}").status_code == 204
    assert client.get(f"/topologies/{tid}").status_code == 404
