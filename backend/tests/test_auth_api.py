"""Auth, users, and project isolation (Step 34)."""

from __future__ import annotations

import uuid

from app.core.security import verify_password
from app.models.user import User


def test_register_login_me_password_hashed(client_strict):
    email = f"u{uuid.uuid4().hex[:8]}@example.com"
    pw = "long-secure-pass-1"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": pw, "display_name": "Test User"},
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    assert token
    uid = r.json()["user"]["id"]

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        row = db.get(User, uuid.UUID(uid))
        assert row is not None
        assert row.password_hash != pw
        assert verify_password(pw, row.password_hash)

    r2 = client_strict.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["user"]["email"] == email.lower()

    r3 = client_strict.post("/auth/login", json={"email": email, "password": pw})
    assert r3.status_code == 200
    assert r3.json()["access_token"]


def test_register_duplicate_email(client_strict):
    email = f"d{uuid.uuid4().hex[:8]}@example.com"
    body = {"email": email, "password": "password123", "display_name": "A"}
    assert client_strict.post("/auth/register", json=body).status_code == 201
    r = client_strict.post("/auth/register", json=body)
    assert r.status_code == 409


def test_strict_unauthenticated_topology_rejected(client_strict):
    assert client_strict.get("/topologies").status_code == 401
    assert client_strict.post("/projects", json={"name": "P"}).status_code == 401


def test_user_cannot_access_other_topology(client_strict):
    # User A
    ra = client_strict.post(
        "/auth/register",
        json={
            "email": f"a{uuid.uuid4().hex[:8]}@example.com",
            "password": "password123",
            "display_name": "A",
        },
    )
    ta = ra.json()["access_token"]
    pa = client_strict.get("/projects", headers={"Authorization": f"Bearer {ta}"}).json()
    pid_a = pa[0]["id"]

    rtop = client_strict.post(
        "/topologies",
        headers={"Authorization": f"Bearer {ta}"},
        json={
            "name": "Secret",
            "project_id": pid_a,
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    assert rtop.status_code == 201
    tid = rtop.json()["id"]

    # User B
    rb = client_strict.post(
        "/auth/register",
        json={
            "email": f"b{uuid.uuid4().hex[:8]}@example.com",
            "password": "password123",
            "display_name": "B",
        },
    )
    tb = rb.json()["access_token"]

    r404 = client_strict.get(f"/topologies/{tid}", headers={"Authorization": f"Bearer {tb}"})
    assert r404.status_code == 404


def test_project_scoped_topology_list_create(client_strict):
    r = client_strict.post(
        "/auth/register",
        json={
            "email": f"c{uuid.uuid4().hex[:8]}@example.com",
            "password": "password123",
            "display_name": "C",
        },
    )
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    plist = client_strict.get("/projects", headers=h).json()
    pid = plist[0]["id"]

    p2 = client_strict.post("/projects", json={"name": "Second"}, headers=h)
    assert p2.status_code == 201
    pid2 = p2.json()["id"]

    t1 = client_strict.post(
        "/topologies",
        headers=h,
        json={
            "name": "In first",
            "project_id": pid,
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    assert t1.status_code == 201
    t2 = client_strict.post(
        "/topologies",
        headers=h,
        json={
            "name": "In second",
            "project_id": pid2,
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    assert t2.status_code == 201

    only_first = client_strict.get(f"/topologies?project_id={pid}", headers=h).json()
    names = {x["name"] for x in only_first}
    assert names == {"In first"}

    all_rows = client_strict.get("/topologies", headers=h).json()
    assert len(all_rows) >= 2


def test_health_public_without_auth(client_strict):
    assert client_strict.get("/health").status_code == 200
