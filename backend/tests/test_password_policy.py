"""Password hashing and bcrypt policy (see app.core.security)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.security import hash_password, verify_password
from app.db.bootstrap import DEV_USER_EMAIL, ensure_dev_user_and_project


def test_hash_password_verify_roundtrip_normal():
    pw = "a-normal-passphrase-9"
    h = hash_password(pw)
    assert h != pw
    assert verify_password(pw, h)
    assert not verify_password(pw + "x", h)


def test_hash_password_verify_roundtrip_over_72_bytes():
    """Internal normalization: bcrypt never sees >72 bytes."""
    pw = "z" * 200
    h = hash_password(pw)
    assert verify_password(pw, h)
    assert not verify_password("z" * 199 + "y", h)


def test_register_rejects_password_over_72_bytes(client_strict: TestClient):
    email = f"z{uuid.uuid4().hex[:8]}@example.com"
    pw = "a" * 73
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": pw, "display_name": "Z"},
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "72" in str(detail).lower()


def test_register_rejects_password_over_72_utf8_bytes_not_ascii_length(client_strict: TestClient):
    """Few characters can still exceed 72 UTF-8 bytes (bcrypt limit)."""
    email = f"e{uuid.uuid4().hex[:8]}@example.com"
    emoji = "😀"
    pw = emoji * 19  # 19 * 4 = 76 UTF-8 bytes
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": pw, "display_name": "E"},
    )
    assert r.status_code == 400


def test_ensure_dev_user_bootstrap_idempotent(engine_db):
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        u1, p1 = ensure_dev_user_and_project(db)
        assert u1.email == DEV_USER_EMAIL
        assert p1.name
    with SessionLocal() as db:
        u2, p2 = ensure_dev_user_and_project(db)
        assert u2.id == u1.id
        assert p2.id == p1.id
