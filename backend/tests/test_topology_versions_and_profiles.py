"""Tests for topology versions and deployment profiles (Step 56)."""

from __future__ import annotations

import uuid

from app.models.topology import NodeType
from app.services.topology_version_diff_service import diff_topology_snapshots

TOPOLOGY_BODY = {
    "name": "Version Lab",
    "description": "version tests",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _register(client, prefix: str = "v") -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "V"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _topology_with_node(client, headers) -> tuple[str, str]:
    r = client.post("/topologies", headers=headers, json=TOPOLOGY_BODY)
    assert r.status_code == 201
    tid = r.json()["id"]
    nr = client.post(
        f"/topologies/{tid}/nodes",
        headers=headers,
        json={
            "name": "web",
            "node_type": NodeType.HOST.value,
            "image": "nginx:latest",
            "ip_address": "10.0.0.2",
            "config": {"env": {"API_KEY": "super-secret-value", "PORT": "8080"}},
        },
    )
    assert nr.status_code == 201
    return tid, nr.json()["id"]


def test_create_list_get_versions(client_strict):
    h = _register(client_strict)
    tid, _ = _topology_with_node(client_strict, h)

    cr = client_strict.post(
        f"/topologies/{tid}/versions",
        headers=h,
        json={"name": "Baseline", "description": "before changes"},
    )
    assert cr.status_code == 201, cr.text
    v1 = cr.json()
    assert v1["version_number"] == 1
    assert v1["source"] == "manual"

    cr2 = client_strict.post(f"/topologies/{tid}/versions", headers=h, json={"name": "Second"})
    assert cr2.status_code == 201
    assert cr2.json()["version_number"] == 2

    lst = client_strict.get(f"/topologies/{tid}/versions", headers=h)
    assert lst.status_code == 200
    assert len(lst.json()["items"]) == 2

    detail = client_strict.get(f"/topologies/{tid}/versions/{v1['id']}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["snapshot_json"]["nodes"]


def test_diff_masks_secrets_and_detects_env_changes():
    left = {
        "topology": {"runtime_target": "docker", "networking_mode": "docker_bridge", "config": {}},
        "nodes": [
            {
                "id": "a",
                "name": "web",
                "node_type": "host",
                "config": {"env": {"API_KEY": "old-secret", "PORT": "80"}},
            }
        ],
        "links": [],
    }
    right = {
        "topology": {"runtime_target": "docker", "networking_mode": "docker_bridge", "config": {}},
        "nodes": [
            {
                "id": "a",
                "name": "web",
                "node_type": "host",
                "config": {"env": {"API_KEY": "new-secret", "PORT": "8080"}},
            },
            {
                "id": "b",
                "name": "db",
                "node_type": "host",
                "config": {},
            },
        ],
        "links": [],
    }
    diff = diff_topology_snapshots(left, right)
    assert diff["nodes"]["added"]
    assert "web" in diff["env_vars"]
    assert diff["env_vars"]["web"]["changed"]["API_KEY"]["before"] == "[redacted]"
    assert diff["env_vars"]["web"]["changed"]["API_KEY"]["after"] == "[redacted]"


def test_rollback_creates_version_and_updates_topology(client_strict):
    h = _register(client_strict)
    tid, nid = _topology_with_node(client_strict, h)

    v = client_strict.post(f"/topologies/{tid}/versions", headers=h, json={"name": "snap"}).json()

    client_strict.patch(
        f"/topologies/{tid}/nodes/{nid}",
        headers=h,
        json={"name": "web-renamed"},
    )

    rb = client_strict.post(f"/topologies/{tid}/versions/{v['id']}/rollback", headers=h)
    assert rb.status_code == 200, rb.text
    assert rb.json()["version"]["source"] == "rollback"

    nodes = client_strict.get(f"/topologies/{tid}/nodes", headers=h).json()
    assert any(n["name"] == "web" for n in nodes)

    versions = client_strict.get(f"/topologies/{tid}/versions", headers=h).json()["items"]
    assert any(x["source"] == "rollback" for x in versions)


def test_profiles_crud_and_default(client_strict):
    h = _register(client_strict)
    tid, _ = _topology_with_node(client_strict, h)

    cr = client_strict.post(
        f"/topologies/{tid}/profiles",
        headers=h,
        json={
            "name": "Dev",
            "profile_type": "dev",
            "config_json": {"env_overrides": {"web": {"DEBUG": "1"}}},
        },
    )
    assert cr.status_code == 201, cr.text
    pid = cr.json()["id"]

    cr2 = client_strict.post(
        f"/topologies/{tid}/profiles",
        headers=h,
        json={"name": "Staging", "profile_type": "staging", "config_json": {}},
    )
    assert cr2.status_code == 201
    sid = cr2.json()["id"]

    def_res = client_strict.post(f"/topologies/{tid}/profiles/{sid}/set-default", headers=h)
    assert def_res.status_code == 200
    assert def_res.json()["is_default"] is True

    lst = client_strict.get(f"/topologies/{tid}/profiles", headers=h).json()["items"]
    defaults = [p for p in lst if p["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == sid

    del_r = client_strict.delete(f"/topologies/{tid}/profiles/{pid}", headers=h)
    assert del_r.status_code == 204


def test_deploy_with_profile_stores_effective_config(client_strict):
    h = _register(client_strict)
    tid, _ = _topology_with_node(client_strict, h)

    pr = client_strict.post(
        f"/topologies/{tid}/profiles",
        headers=h,
        json={
            "name": "Dev overrides",
            "profile_type": "dev",
            "config_json": {"env_overrides": {"web": {"EXTRA": "yes"}}},
        },
    )
    profile_id = pr.json()["id"]

    dep = client_strict.post(
        f"/topologies/{tid}/deploy",
        headers=h,
        json={"profile_id": profile_id},
    )
    assert dep.status_code == 201, dep.text
    body = dep.json()
    assert body["deployment_profile_id"] == profile_id
    assert body["topology_version_id"]
    assert body["effective_config_json"]
    env_nodes = body["effective_config_json"]["nodes"]
    web = next(n for n in env_nodes if n["name"] == "web")
    assert web["config"]["env"].get("EXTRA") == "yes"
    assert "super-secret" not in str(body["effective_config_json"])


def test_viewer_can_list_versions_member_can_create(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    owner_h = _register(client_strict, "own")
    viewer_email = f"v{uuid.uuid4().hex[:8]}@example.com"
    vr = client_strict.post(
        "/auth/register",
        json={"email": viewer_email, "password": "password123", "display_name": "Viewer"},
    )
    viewer_h = {"Authorization": f"Bearer {vr.json()['access_token']}"}
    pid = client_strict.get("/projects", headers=owner_h).json()[0]["id"]
    inv = client_strict.post(
        f"/projects/{pid}/invitations",
        headers=owner_h,
        json={"email": viewer_email, "role": "viewer"},
    )
    token = inv.json()["accept_token"]
    client_strict.post(f"/invitations/{token}/accept", headers=viewer_h)

    tid = client_strict.post("/topologies", headers=owner_h, json=TOPOLOGY_BODY).json()["id"]

    deny = client_strict.post(f"/topologies/{tid}/versions", headers=viewer_h, json={"name": "nope"})
    assert deny.status_code == 403

    ok = client_strict.get(f"/topologies/{tid}/versions", headers=viewer_h)
    assert ok.status_code == 200


def test_member_cannot_delete_profile_owner_can(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    owner_h = _register(client_strict, "o2")
    member_email = f"m{uuid.uuid4().hex[:8]}@example.com"
    mr = client_strict.post(
        "/auth/register",
        json={"email": member_email, "password": "password123", "display_name": "M"},
    )
    member_h = {"Authorization": f"Bearer {mr.json()['access_token']}"}
    pid = client_strict.get("/projects", headers=owner_h).json()[0]["id"]
    inv = client_strict.post(
        f"/projects/{pid}/invitations",
        headers=owner_h,
        json={"email": member_email, "role": "member"},
    )
    client_strict.post(f"/invitations/{inv.json()['accept_token']}/accept", headers=member_h)

    tid = client_strict.post("/topologies", headers=owner_h, json=TOPOLOGY_BODY).json()["id"]
    pr = client_strict.post(
        f"/topologies/{tid}/profiles",
        headers=member_h,
        json={"name": "Dev", "profile_type": "dev", "config_json": {}},
    )
    assert pr.status_code == 201
    profile_id = pr.json()["id"]

    deny = client_strict.delete(f"/topologies/{tid}/profiles/{profile_id}", headers=member_h)
    assert deny.status_code == 403

    ok = client_strict.delete(f"/topologies/{tid}/profiles/{profile_id}", headers=owner_h)
    assert ok.status_code == 204
