"""Project membership and RBAC (Step 36)."""

from __future__ import annotations

import uuid

from app.models.topology import NodeType


def _register(client, prefix: str = "u") -> tuple[str, str, dict[str, str]]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    return email, tok, {"Authorization": f"Bearer {tok}"}


def test_creator_becomes_owner(client_strict):
    _, _, h = _register(client_strict)
    plist = client_strict.get("/projects", headers=h).json()
    assert len(plist) >= 1
    assert plist[0]["my_role"] == "owner"


def test_owner_can_invite_existing_user(client_strict):
    _, _, ha = _register(client_strict, "oa")
    eb, _, _ = _register(client_strict, "ob")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    inv = client_strict.post(
        f"/projects/{pid}/members/invite",
        headers=ha,
        json={"email": eb, "role": "member"},
    )
    assert inv.status_code == 201, inv.text
    members = client_strict.get(f"/projects/{pid}/members", headers=ha).json()
    emails = {m["email"] for m in members}
    assert eb in emails


def test_duplicate_invite_rejected(client_strict):
    _, _, ha = _register(client_strict, "da")
    eb, _, _ = _register(client_strict, "db")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=ha,
            json={"email": eb, "role": "viewer"},
        ).status_code
        == 201
    )
    r2 = client_strict.post(
        f"/projects/{pid}/members/invite",
        headers=ha,
        json={"email": eb, "role": "member"},
    )
    assert r2.status_code == 409


def test_invite_unknown_email_message(client_strict):
    _, _, ha = _register(client_strict, "ua")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    r = client_strict.post(
        f"/projects/{pid}/members/invite",
        headers=ha,
        json={"email": f"ghost-{uuid.uuid4().hex}@example.com", "role": "member"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "No user with that email exists yet."


def test_non_member_cannot_access_project(client_strict):
    _, _, ha = _register(client_strict, "na")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    _, _, hb = _register(client_strict, "nb")
    assert client_strict.get(f"/projects/{pid}", headers=hb).status_code == 404


def test_viewer_cannot_create_topology(client_strict):
    _, _, ha = _register(client_strict, "va")
    eb, tb, hb = _register(client_strict, "vb")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=ha,
            json={"email": eb, "role": "viewer"},
        ).status_code
        == 201
    )
    r = client_strict.post(
        "/topologies",
        headers=hb,
        json={
            "name": "X",
            "project_id": pid,
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    assert r.status_code == 403


def test_member_can_create_topology(client_strict):
    _, _, ha = _register(client_strict, "ma")
    eb, tb, hb = _register(client_strict, "mb")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=ha,
            json={"email": eb, "role": "member"},
        ).status_code
        == 201
    )
    r = client_strict.post(
        "/topologies",
        headers=hb,
        json={
            "name": "Member topo",
            "project_id": pid,
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    assert r.status_code == 201


def test_member_cannot_delete_project(client_strict):
    _, _, ha = _register(client_strict, "pa")
    eb, tb, hb = _register(client_strict, "pb")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=ha,
            json={"email": eb, "role": "member"},
        ).status_code
        == 201
    )
    assert client_strict.delete(f"/projects/{pid}", headers=hb).status_code == 403


def test_owner_can_remove_member(client_strict):
    _, _, ha = _register(client_strict, "ra")
    eb, _, hb = _register(client_strict, "rb")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=ha,
            json={"email": eb, "role": "member"},
        ).status_code
        == 201
    )
    members = client_strict.get(f"/projects/{pid}/members", headers=ha).json()
    uid_b = client_strict.get("/auth/me", headers=hb).json()["user"]["id"]
    mid = next(m["id"] for m in members if m["user_id"] == uid_b)
    dr = client_strict.delete(f"/projects/{pid}/members/{mid}", headers=ha)
    assert dr.status_code == 204
    assert client_strict.get(f"/projects/{pid}", headers=hb).status_code == 404


def test_owner_cannot_remove_self_if_only_owner(client_strict):
    _, _, h = _register(client_strict, "so")
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    uid = client_strict.get("/auth/me", headers=h).json()["user"]["id"]
    members = client_strict.get(f"/projects/{pid}/members", headers=h).json()
    mid = next(m["id"] for m in members if m["user_id"] == uid)
    r = client_strict.delete(f"/projects/{pid}/members/{mid}", headers=h)
    assert r.status_code == 400
    assert "only project owner" in r.json()["detail"].lower()


def test_viewer_can_list_topology_but_not_mutate_nodes(client_strict):
    _, _, ha = _register(client_strict, "qa")
    eb, tb, hb = _register(client_strict, "qb")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    tr = client_strict.post(
        "/topologies",
        headers=ha,
        json={
            "name": "Shared",
            "project_id": pid,
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    assert tr.status_code == 201
    tid = tr.json()["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=ha,
            json={"email": eb, "role": "viewer"},
        ).status_code
        == 201
    )
    assert client_strict.get(f"/topologies/{tid}", headers=hb).status_code == 200
    assert (
        client_strict.post(
            f"/topologies/{tid}/nodes",
            headers=hb,
            json={
                "name": "n",
                "node_type": NodeType.HOST.value,
                "image": None,
                "ip_address": None,
                "config": None,
            },
        ).status_code
        == 403
    )


def test_member_cannot_invite(client_strict):
    _, _, ha = _register(client_strict, "ia")
    eb, _, hb = _register(client_strict, "ib")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=ha,
            json={"email": eb, "role": "member"},
        ).status_code
        == 201
    )
    ghost = f"nope-{uuid.uuid4().hex[:6]}@example.com"
    r = client_strict.post(
        f"/projects/{pid}/members/invite",
        headers=hb,
        json={"email": ghost, "role": "viewer"},
    )
    assert r.status_code == 403
