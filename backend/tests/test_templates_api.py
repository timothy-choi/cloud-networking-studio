"""Runtime templates API (Step 43) — CRUD, clone, RBAC."""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.topology import NodeType
from app.models.runtime_template import RuntimeTemplate


def _reg(client_strict, prefix: str) -> tuple[str, dict[str, str]]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


from tests.membership_helpers import invite_and_accept


def _project_topology(client_strict, *, invite_role: str | None = None):
    """Owner + optional invitee with role; returns headers and ids."""
    _, ha = _reg(client_strict, "tp")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    hb: dict[str, str] | None = None
    if invite_role:
        eb, hb = _reg(client_strict, "tpi")
        invite_and_accept(client_strict, ha, pid, eb, hb, invite_role)
    tid = client_strict.post(
        "/topologies",
        headers=ha,
        json={
            "name": "Lab",
            "project_id": pid,
            "description": "d",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).json()["id"]
    client_strict.post(
        f"/topologies/{tid}/nodes",
        headers=ha,
        json={
            "name": "a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    return ha, hb, pid, tid


def test_templates_list_includes_starters(client_strict):
    ha, _, _, _ = _project_topology(client_strict)
    r = client_strict.get("/templates", headers=ha)
    assert r.status_code == 200, r.text
    slugs = {x.get("slug") for x in r.json() if x.get("slug")}
    assert "client-service" in slugs
    assert "gateway-api-db" in slugs
    assert "failure-injection-lab" in slugs


def test_create_list_clone_project_template(client_strict):
    ha, _, pid, tid = _project_topology(client_strict)
    cr = client_strict.post(
        f"/templates/from-topology/{tid}",
        headers=ha,
        json={
            "name": "My tpl",
            "description": "x",
            "category": "lab",
            "tags": ["a", "b"],
            "visibility": "project",
        },
    )
    assert cr.status_code == 201, cr.text
    tpl_id = cr.json()["id"]
    lst = client_strict.get("/templates", headers=ha)
    assert any(x["id"] == tpl_id for x in lst.json())

    cl = client_strict.post(
        f"/templates/{tpl_id}/clone",
        headers=ha,
        json={"name": "Cloned topo", "project_id": pid},
    )
    assert cl.status_code == 201, cl.text
    new_id = cl.json()["id"]
    nodes = client_strict.get(f"/topologies/{new_id}/nodes", headers=ha).json()
    assert len(nodes) >= 1


def test_viewer_cannot_create_template(client_strict):
    ha, hb, _, tid = _project_topology(client_strict, invite_role="viewer")
    r = client_strict.post(
        f"/templates/from-topology/{tid}",
        headers=hb,
        json={
            "name": "nope",
            "visibility": "private",
            "category": "x",
            "tags": [],
        },
    )
    assert r.status_code == 403


def test_viewer_can_list_templates(client_strict):
    ha, hb, _, tid = _project_topology(client_strict, invite_role="viewer")
    assert client_strict.post(
        f"/templates/from-topology/{tid}",
        headers=ha,
        json={"name": "Shared", "visibility": "project", "category": "c", "tags": []},
    ).status_code == 201
    r = client_strict.get("/templates", headers=hb)
    assert r.status_code == 200
    assert any(x.get("name") == "Shared" for x in r.json())


def test_viewer_cannot_clone(client_strict):
    ha, hb, pid, tid = _project_topology(client_strict, invite_role="viewer")
    tpl = client_strict.post(
        f"/templates/from-topology/{tid}",
        headers=ha,
        json={"name": "T", "visibility": "project", "category": "c", "tags": []},
    ).json()
    r = client_strict.post(
        f"/templates/{tpl['id']}/clone",
        headers=hb,
        json={"project_id": pid},
    )
    assert r.status_code == 403


def test_client_service_starter_snapshot_http_lab(client_strict):
    """Built-in client + server template uses nginx + alpine with wget for reliable HTTP traffic tests."""
    ha, _, pid, _ = _project_topology(client_strict)
    with SessionLocal() as db:
        tpl_id = db.scalar(select(RuntimeTemplate.id).where(RuntimeTemplate.slug == "client-service"))
    assert tpl_id is not None
    cl = client_strict.post(
        f"/templates/{tpl_id}/clone",
        headers=ha,
        json={"name": "cloned-http-lab", "project_id": pid},
    )
    assert cl.status_code == 201, cl.text
    tid = cl.json()["id"]
    nodes = client_strict.get(f"/topologies/{tid}/nodes", headers=ha).json()
    by_name = {n["name"]: n for n in nodes}
    assert "client" in by_name and "server" in by_name
    assert by_name["client"]["image"] == "alpine:3.19"
    assert "nginx" in (by_name["server"]["image"] or "").lower()
    assert by_name["client"]["node_type"] == "generic"
    assert by_name["server"]["node_type"] == "generic"
    links = client_strict.get(f"/topologies/{tid}/links", headers=ha).json()
    assert len(links) == 1


def test_delete_built_in_forbidden(client_strict):
    ha, _, _, _ = _project_topology(client_strict)
    with SessionLocal() as db:
        bid = db.scalar(select(RuntimeTemplate.id).where(RuntimeTemplate.slug == "client-service"))
    assert bid is not None
    r = client_strict.delete(f"/templates/{bid}", headers=ha)
    assert r.status_code == 403


def test_creator_can_delete_own_template(client_strict):
    ha, _, _, tid = _project_topology(client_strict)
    tpl = client_strict.post(
        f"/templates/from-topology/{tid}",
        headers=ha,
        json={"name": "Delme", "visibility": "private", "category": "c", "tags": []},
    ).json()
    r = client_strict.delete(f"/templates/{tpl['id']}", headers=ha)
    assert r.status_code == 204


def test_project_owner_can_delete_member_project_template(client_strict):
    ha, hb, _pid, tid = _project_topology(client_strict, invite_role="member")
    tpl = client_strict.post(
        f"/templates/from-topology/{tid}",
        headers=hb,
        json={"name": "Member tpl", "visibility": "project", "category": "c", "tags": []},
    ).json()
    assert tpl.get("owner_user_id") is not None
    r = client_strict.delete(f"/templates/{tpl['id']}", headers=ha)
    assert r.status_code == 204


def test_member_cannot_delete_others_template_only_owner_or_creator(client_strict):
    ha, hb, pid, tid = _project_topology(client_strict, invite_role="member")
    tpl = client_strict.post(
        f"/templates/from-topology/{tid}",
        headers=ha,
        json={"name": "Owner tpl", "visibility": "project", "category": "c", "tags": []},
    ).json()
    r = client_strict.delete(f"/templates/{tpl['id']}", headers=hb)
    assert r.status_code == 403
    ro = client_strict.delete(f"/templates/{tpl['id']}", headers=ha)
    assert ro.status_code == 204
