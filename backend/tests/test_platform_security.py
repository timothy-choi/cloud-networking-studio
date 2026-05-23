"""Security hardening: scopes, masking, production validation (Step 53D)."""

from __future__ import annotations

import uuid

import pytest

from app.core.secret_masking import mask_secrets_in_text, scrub_sensitive_dict
from app.core.security_validation import is_weak_auth_secret, validate_production_security
from app.models.topology import NodeType
from app.services.audit_service import record_audit


def _reg(client_strict, prefix: str) -> tuple[dict[str, str], str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "S"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    return h, pid


def test_scoped_token_read_projects_only(client_strict):
    hj, _ = _reg(client_strict, "sr")
    cr = client_strict.post(
        "/api-tokens",
        headers=hj,
        json={"name": "read-only", "scopes": ["read:projects"]},
    )
    assert cr.status_code == 201, cr.text
    token = cr.json()["token"]
    hp = {"Authorization": f"Bearer {token}"}

    assert client_strict.get("/projects", headers=hp).status_code == 200
    assert client_strict.post(
        "/topologies",
        headers=hp,
        json={
            "name": "blocked",
            "description": "x",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).status_code == 403


def test_scoped_token_deploy_scope(client_strict):
    hj, _ = _reg(client_strict, "sd")
    cr = client_strict.post(
        "/api-tokens",
        headers=hj,
        json={"name": "deploy", "scopes": ["read:projects", "write:topologies", "deploy:deployments"]},
    )
    assert cr.status_code == 201, cr.text
    hp = {"Authorization": f"Bearer {cr.json()['token']}"}

    topo = client_strict.post(
        "/topologies",
        headers=hp,
        json={
            "name": "Deploy lab",
            "description": "x",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    assert topo.status_code == 201, topo.text
    tid = topo.json()["id"]
    client_strict.post(
        f"/topologies/{tid}/nodes",
        headers=hp,
        json={
            "name": "n1",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    assert client_strict.post(f"/topologies/{tid}/deploy", headers=hp).status_code == 201


def test_api_token_cannot_create_tokens(client_strict):
    hj, _ = _reg(client_strict, "st")
    cr = client_strict.post(
        "/api-tokens",
        headers=hj,
        json={"name": "full", "scopes": ["admin:project"]},
    )
    assert cr.status_code == 201, cr.text
    hp = {"Authorization": f"Bearer {cr.json()['token']}"}
    assert client_strict.post("/api-tokens", headers=hp, json={"name": "nope"}).status_code == 403


def test_legacy_token_without_scopes_has_full_access(client_strict):
    _, h = _reg(client_strict, "lg")
    cr = client_strict.post("/api-tokens", headers=h, json={"name": "legacy"})
    assert cr.status_code == 201, cr.text
    hp = {"Authorization": f"Bearer {cr.json()['token']}"}
    assert client_strict.get("/projects", headers=hp).status_code == 200
    assert client_strict.post(
        "/topologies",
        headers=hp,
        json={
            "name": "legacy lab",
            "description": "x",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).status_code == 201


def test_secret_masking_masks_jwt_and_tokens():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    masked = mask_secrets_in_text(f"Bearer {jwt}")
    assert jwt not in (masked or "")
    assert "[redacted" in (masked or "")

    api_tok = f"{uuid.uuid4()}.abcdefghijklmnopqrstuvwxyz123456"
    masked2 = mask_secrets_in_text(api_tok)
    assert "abcdefghijklmnopqrstuvwxyz123456" not in (masked2 or "")

    scrubbed = scrub_sensitive_dict({"password": "secret123", "note": "ok"})
    assert scrubbed["password"] == "[redacted]"
    assert scrubbed["note"] == "ok"


def test_audit_metadata_scrubs_secrets(client, engine_db):
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        row = record_audit(
            db,
            action="test.secret",
            resource_type="test",
            metadata={"token": "abc123", "message": "fine"},
            commit=True,
        )
        assert row.metadata_json["token"] == "[redacted]"
        assert row.metadata_json["message"] == "fine"


def test_weak_production_secret_rejected(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("CNS_ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "local-dev-only-change-AUTH_SECRET_KEY-in-production-min-32-chars")
    s = Settings()
    _, errors = validate_production_security(s)
    assert any("AUTH_SECRET_KEY" in e for e in errors)
    assert is_weak_auth_secret(s.auth_secret_key)


def test_security_status_endpoint(client):
    r = client.get("/platform/security-status")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "auth_secret_configured",
        "auth_secret_strong",
        "cors_strict",
        "api_token_scopes_enabled",
        "audit_logging_enabled",
        "runtime_provider_access_configured",
    ):
        assert key in body


def test_startup_security_warns_on_wildcard_cors(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("CNS_ENVIRONMENT", "development")
    monkeypatch.setenv("CNS_CORS_ORIGINS", "*")
    s = Settings()
    warnings, errors = validate_production_security(s)
    assert not errors
    assert any("wildcard" in w.lower() for w in warnings)
