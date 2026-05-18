"""API tokens and Bearer auth (Step 44)."""

from __future__ import annotations

import uuid

import pytest


def _reg(client_strict, prefix: str) -> tuple[str, dict[str, str]]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_api_token_create_list_revoke(client_strict):
    _, h = _reg(client_strict, "tok")
    cr = client_strict.post("/api-tokens", headers=h, json={"name": "ci"})
    assert cr.status_code == 201, cr.text
    body = cr.json()
    assert "token" in body and "." in body["token"]
    tid = body["id"]
    lst = client_strict.get("/api-tokens", headers=h)
    assert lst.status_code == 200
    assert any(x["id"] == tid for x in lst.json())

    raw = body["token"]
    hp = {"Authorization": f"Bearer {raw}"}
    me = client_strict.get("/auth/me", headers=hp)
    assert me.status_code == 200, me.text

    pr = client_strict.get("/projects", headers=hp)
    assert pr.status_code == 200, pr.text

    assert client_strict.delete(f"/api-tokens/{tid}", headers=h).status_code == 204

    fail = client_strict.get("/projects", headers=hp)
    assert fail.status_code == 401


def test_second_token_still_works_after_revoking_first(client_strict):
    _, h = _reg(client_strict, "tok2")
    first = client_strict.post("/api-tokens", headers=h, json={"name": "a"}).json()
    second = client_strict.post("/api-tokens", headers=h, json={"name": "b"}).json()
    assert client_strict.delete(f"/api-tokens/{first['id']}", headers=h).status_code == 204
    assert client_strict.get("/auth/me", headers={"Authorization": f"Bearer {second['token']}"}).status_code == 200
