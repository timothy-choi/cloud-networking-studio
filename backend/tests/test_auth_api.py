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


def test_auth_me_requires_bearer_without_token(client):
    """GET /auth/me never uses the implicit dev user; missing Authorization → 401."""
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_auth_me_ok_with_bearer_after_register(client):
    email = f"m{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "M"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email.lower()


def _login_fail_body() -> dict:
    return {"detail": "Invalid email or password"}


def _login_fail_comparable(body: dict) -> dict:
    """Stable subset of structured login failures (ignores per-request IDs)."""
    assert body["detail"] == "Invalid email or password"
    err = body.get("error") or {}
    assert err.get("code") == "AUTH_REQUIRED"
    assert err.get("message") == "Invalid email or password"
    assert body.get("request_id")
    assert err.get("request_id")
    return {
        "detail": body["detail"],
        "status": body.get("status"),
        "error": {
            "code": err.get("code"),
            "message": err.get("message"),
            "details": err.get("details") or {},
        },
    }


def _assert_login_fail_response(r) -> None:
    assert r.status_code == 401
    _login_fail_comparable(r.json())


def test_login_unknown_email_returns_401_not_500(client):
    """Regression: unknown email must not surface ORM/lookup bugs as HTTP 500."""
    email = f"ghost-{uuid.uuid4().hex}@example.com"
    r = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert r.status_code != 500
    assert r.status_code == 401
    _assert_login_fail_response(r)


def test_login_invalid_json_body_not_500(client):
    r = client.post(
        "/auth/login",
        content=b"not-json{",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code != 500


def test_login_missing_password_returns_422_not_500(client):
    r = client.post("/auth/login", json={"email": "someone@example.com"})
    assert r.status_code != 500
    assert r.status_code == 422


def test_login_corrupt_password_hash_returns_401(client):
    from sqlalchemy import text

    from app.db.session import SessionLocal

    email = f"badhash{uuid.uuid4().hex[:8]}@example.com"
    assert (
        client.post(
            "/auth/register",
            json={"email": email, "password": "password123", "display_name": "X"},
        ).status_code
        == 201
    )
    with SessionLocal() as db:
        db.execute(
            text("UPDATE users SET password_hash = :h WHERE email = :e"),
            {"h": "#$%not-a-valid-bcrypt-string", "e": email},
        )
        db.commit()
    r = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 401
    _assert_login_fail_response(r)


def test_login_wrong_password_returns_401(client):
    email = f"lp{uuid.uuid4().hex[:8]}@example.com"
    assert (
        client.post(
            "/auth/register",
            json={"email": email, "password": "correct-pass-9", "display_name": "LP"},
        ).status_code
        == 201
    )
    r = client.post("/auth/login", json={"email": email, "password": "wrong-pass-9"})
    assert r.status_code == 401
    _assert_login_fail_response(r)


def test_login_unknown_vs_wrong_password_same_response(client):
    """Do not reveal whether the email exists (identical JSON body)."""
    email = f"cmp{uuid.uuid4().hex[:8]}@example.com"
    assert (
        client.post(
            "/auth/register",
            json={"email": email, "password": "secret-pass-1", "display_name": "CMP"},
        ).status_code
        == 201
    )
    unknown = client.post(
        "/auth/login",
        json={"email": "other-unknown@example.com", "password": "secret-pass-1"},
    )
    wrong_pw = client.post(
        "/auth/login",
        json={"email": email, "password": "not-the-secret"},
    )
    assert unknown.status_code == 401
    assert wrong_pw.status_code == 401
    assert _login_fail_comparable(unknown.json()) == _login_fail_comparable(wrong_pw.json())


def test_login_success_returns_token_and_user(client):
    email = f"ok{uuid.uuid4().hex[:8]}@example.com"
    assert (
        client.post(
            "/auth/register",
            json={"email": email, "password": "password123", "display_name": "OK"},
        ).status_code
        == 201
    )
    r2 = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["access_token"]
    assert data["user"]["email"] == email.lower()
