"""Freeform topology deploy — backward compatible with legacy nodes."""

from __future__ import annotations

import uuid

from app.models.topology import NodeType
from app.services.deployment_planner import build_deployment_plan
from app.services.node_runtime_config import primary_port


TOPO_BODY = {
    "name": "Freeform Lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _two_node_topology(client, *, custom: bool = False):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    na_body = {
        "name": "legacy-a",
        "node_type": NodeType.GENERIC.value,
        "image": "nginx:alpine",
        "ip_address": "10.8.0.10",
        "config": None,
    }
    nb_body = {
        "name": "legacy-b",
        "node_type": NodeType.HOST.value,
        "image": "alpine:latest",
        "ip_address": "10.8.0.11",
        "config": None,
    }
    if custom:
        nb_body = {
            "name": "custom-api",
            "node_type": NodeType.GENERIC.value,
            "image": "busybox:latest",
            "ip_address": "10.8.0.12",
            "config": {
                "role_label": "api",
                "command": "sh -c 'sleep infinity'",
                "ports": [{"port": 8080, "target_port": 8080}],
                "env": {"LAB": "1"},
                "terminal_enabled": True,
                "health_check": "/",
                "description": "custom workload",
            },
        }
    na = client.post(f"/topologies/{tid}/nodes", json=na_body).json()
    nb = client.post(f"/topologies/{tid}/nodes", json=nb_body).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": na["id"],
            "target_node_id": nb["id"],
            "network_name": "lab-net",
            "cidr": "10.8.0.0/24",
            "config": None,
        },
    )
    return tid


def test_custom_node_config_persisted_and_returned(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    body = {
        "name": "api",
        "node_type": NodeType.GENERIC.value,
        "image": "busybox:latest",
        "ip_address": "10.8.0.50",
        "config": {
            "role_label": "api",
            "command": "sleep infinity",
            "ports": [{"port": 9090, "target_port": 9090}],
            "env": {"LAB": "yes"},
            "terminal_enabled": False,
            "health_check": "/healthz",
        },
    }
    created = client.post(f"/topologies/{tid}/nodes", json=body)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["image"] == "busybox:latest"
    assert row["ip_address"] == "10.8.0.50"
    cfg = row["config"]
    assert cfg["role_label"] == "api"
    assert cfg["env"] == {"LAB": "yes"}
    assert cfg["ports"][0]["port"] == 9090
    assert cfg["terminal_enabled"] is False

    listed = client.get(f"/topologies/{tid}/nodes").json()
    assert any(n["name"] == "api" and n["config"]["role_label"] == "api" for n in listed)


def test_invalid_node_image_rejected(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    r = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "bad",
            "node_type": NodeType.HOST.value,
            "image": "not valid image!!!",
            "config": None,
        },
    )
    assert r.status_code == 422


def test_invalid_ports_rejected(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    r = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "bad",
            "node_type": NodeType.HOST.value,
            "config": {"ports": [{"port": 99999}]},
        },
    )
    assert r.status_code == 422


def test_runtime_access_shows_env_and_health(client):
    tid = _two_node_topology(client, custom=True)
    did = client.post(f"/topologies/{tid}/deploy").json()["id"]
    nodes = client.get(f"/deployments/{did}/runtime/nodes").json()["nodes"]
    custom = next(n for n in nodes if n.get("name") == "custom-api")
    meta = custom.get("metadata") or {}
    assert meta.get("env")
    assert meta.get("health_check_path") == "/"
    assert meta.get("intended_ip") == "10.8.0.12"


def test_legacy_topology_still_deploys(client):
    tid = _two_node_topology(client, custom=False)
    r = client.post(f"/topologies/{tid}/deploy")
    assert r.status_code == 201, r.text


def test_custom_node_deploys_with_runtime_access_ports(client):
    tid = _two_node_topology(client, custom=True)
    r = client.post(f"/topologies/{tid}/deploy")
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    svc_sec = client.get(f"/deployments/{did}/runtime/services").json()
    services = svc_sec.get("services") or []
    custom = next((s for s in services if s.get("name") == "custom-api"), None)
    assert custom is not None
    ports = custom.get("ports") or []
    assert any(p.get("port") == 8080 for p in ports)
    meta = custom.get("metadata") or {}
    assert meta.get("role_label") == "api"
    assert meta.get("image") == "busybox:latest"
    assert "sleep" in (meta.get("command") or "")


def test_preset_override_image_in_plan(client):
    """Preset-style node with overridden image is reflected in deployment plan."""
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "svc",
            "node_type": NodeType.GENERIC.value,
            "image": "nginx:alpine",
            "ip_address": "10.9.0.20",
            "config": {
                "role_label": "web",
                "command": "nginx -g 'daemon off;'",
                "ports": [{"port": 443, "target_port": 443}],
            },
        },
    )
    detail = client.get(f"/topologies/{tid}").json()
    assert detail["id"] == tid
    from app.db.session import SessionLocal
    from app.models.topology import Topology
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select

    with SessionLocal() as db:
        topo = db.scalar(
            select(Topology)
            .where(Topology.id == uuid.UUID(tid))
            .options(selectinload(Topology.nodes), selectinload(Topology.links))
        )
        plan = build_deployment_plan(topo)
    node = next(n for n in plan.nodes if n.name == "svc")
    assert node.image == "nginx:alpine"
    assert node.runtime_config is not None
    assert node.runtime_config.command is not None
    assert node.runtime_config.ports[0].port == 443
    assert primary_port(node.runtime_config) == 443


def test_legacy_null_image_gets_default_in_plan(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "legacy-host",
            "node_type": NodeType.HOST.value,
            "image": None,
            "ip_address": "10.8.0.40",
            "config": None,
        },
    )
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "legacy-svc",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": "10.8.0.41",
            "config": None,
        },
    )
    from app.db.session import SessionLocal
    from app.models.topology import Topology
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select

    with SessionLocal() as db:
        topo = db.scalar(
            select(Topology)
            .where(Topology.id == uuid.UUID(tid))
            .options(selectinload(Topology.nodes), selectinload(Topology.links))
        )
        plan = build_deployment_plan(topo)
    by_name = {n.name: n for n in plan.nodes}
    assert by_name["legacy-host"].image == "alpine:latest"
    assert by_name["legacy-svc"].image == "nginx:alpine"


def test_blank_image_rejected_at_deploy(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    node = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "blank-img",
            "node_type": NodeType.HOST.value,
            "image": None,
            "config": None,
        },
    ).json()
    from app.db.session import SessionLocal
    from app.models.topology import TopologyNode

    with SessionLocal() as db:
        row = db.get(TopologyNode, uuid.UUID(node["id"]))
        row.image = ""
        db.commit()

    dep = client.post(f"/topologies/{tid}/deploy")
    assert dep.status_code == 400, dep.text
    body = dep.json()
    assert body["status"] == "failed"
    assert any("image" in (e.get("message") or "").lower() for e in body.get("events") or [])


def test_smoke_like_topology_deploys_with_defaults(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "svc",
            "node_type": NodeType.GENERIC.value,
            "image": "nginx:alpine",
            "ip_address": "10.0.0.2",
            "config": None,
        },
    ).json()["id"]
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "host",
            "node_type": NodeType.HOST.value,
            "image": "alpine:latest",
            "ip_address": "10.0.0.3",
            "config": {"command": ["sleep", "infinity"]},
        },
    ).json()["id"]
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": na,
            "target_node_id": nb,
            "network_name": "net0",
            "cidr": "10.0.0.0/24",
            "config": None,
        },
    )
    dep = client.post(f"/topologies/{tid}/deploy")
    assert dep.status_code == 201, dep.text
    assert dep.json()["status"] == "succeeded"


def test_template_starter_still_clones(client_strict):
    """Existing runtime template library remains usable."""
    _, headers = _register(client_strict)
    starters = client_strict.get("/templates", headers=headers).json()
    slug_ids = {t["slug"]: t["id"] for t in starters if t.get("slug")}
    assert "client-service" in slug_ids
    clone = client_strict.post(
        f"/templates/{slug_ids['client-service']}/clone",
        headers=headers,
        json={"name": "cloned-freeform-test"},
    )
    assert clone.status_code == 201, clone.text
    topo_id = clone.json()["id"]
    deploy = client_strict.post(f"/topologies/{topo_id}/deploy", headers=headers)
    assert deploy.status_code == 201, deploy.text


def _register(client_strict):
    import uuid as _uuid

    email = f"ff{_uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "FF"},
    )
    assert r.status_code == 201
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}
