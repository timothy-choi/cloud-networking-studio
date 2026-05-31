"""Tests for credential profile encryption, ownership, and infra integration."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.core.credential_encryption import decrypt_secret, encrypt_secret
from app.models.credential_profile import CredentialProfile
from app.services import credential_profile_service as profile_svc
from app.services.terraform_credentials_service import (
    is_credential_profile_ref,
    validate_terraform_credentials_ref,
)

GCP_SA = {
    "type": "service_account",
    "project_id": "my-gcp-project",
    "private_key": "-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n",
    "client_email": "cns@test.iam.gserviceaccount.com",
}


def test_encrypt_decrypt_roundtrip():
    plain = json.dumps(GCP_SA)
    encrypted = encrypt_secret(plain)
    assert encrypted != plain
    assert decrypt_secret(encrypted) == plain


def test_credentials_ref_for_profile():
    pid = uuid.uuid4()
    assert profile_svc.credentials_ref_for_profile(pid) == f"credential:{pid}"
    assert is_credential_profile_ref(f"credential:{pid}") is True
    assert is_credential_profile_ref("env:GOOGLE_APPLICATION_CREDENTIALS") is False


def test_create_and_validate_gcp_profile(client_strict, engine_db):
    from app.db.session import SessionLocal
    from app.models.credential_profile import CredentialProfile

    email = f"cred{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Cred User"},
    )
    assert reg.status_code == 201, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]

    create = client_strict.post(
        f"/projects/{project_id}/credential-profiles",
        headers=headers,
        json={
            "name": "My GCP SA",
            "provider": "gcp",
            "credential_type": "gcp_service_account_json",
            "secret": json.dumps(GCP_SA),
            "metadata": {},
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["validation_status"] == "valid"
    assert body["credentials_ref"].startswith("credential:")
    assert "secret" not in body
    assert "encrypted_secret" not in body

    listed = client_strict.get(f"/projects/{project_id}/credential-profiles", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    profile_id = body["id"]
    fetched = client_strict.get(f"/credential-profiles/{profile_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "My GCP SA"

    with SessionLocal() as db:
        row = db.get(CredentialProfile, uuid.UUID(profile_id))
        assert row is not None
        assert row.encrypted_secret != json.dumps(GCP_SA)
        assert decrypt_secret(row.encrypted_secret) == json.dumps(GCP_SA)


def test_credential_profile_ownership_blocks_other_project(client_strict, engine_db):
    email_a = f"owna{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"ownb{uuid.uuid4().hex[:8]}@example.com"
    reg_a = client_strict.post(
        "/auth/register",
        json={"email": email_a, "password": "password123", "display_name": "A"},
    )
    reg_b = client_strict.post(
        "/auth/register",
        json={"email": email_b, "password": "password123", "display_name": "B"},
    )
    ha = {"Authorization": f"Bearer {reg_a.json()['access_token']}"}
    hb = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}
    project_a = client_strict.get("/projects", headers=ha).json()[0]["id"]

    create = client_strict.post(
        f"/projects/{project_a}/credential-profiles",
        headers=ha,
        json={
            "name": "Private GCP",
            "provider": "gcp",
            "credential_type": "gcp_service_account_json",
            "secret": json.dumps(GCP_SA),
        },
    )
    profile_id = create.json()["id"]
    denied = client_strict.get(f"/credential-profiles/{profile_id}", headers=hb)
    assert denied.status_code == 404


def test_materialize_gcp_profile_uses_inline_json_for_runner():
    profile = SimpleNamespace(
        id=uuid.uuid4(),
        provider="gcp",
        credential_type="gcp_service_account_json",
        encrypted_secret=encrypt_secret(json.dumps(GCP_SA)),
        metadata_json={},
    )
    materialized = profile_svc.materialize_profile_credentials(profile)  # type: ignore[arg-type]
    assert materialized.temp_paths == []
    assert "GOOGLE_CREDENTIALS_JSON" in materialized.env
    assert json.loads(materialized.env["GOOGLE_CREDENTIALS_JSON"])["type"] == "service_account"
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in materialized.env
    materialized.cleanup()


def test_materialize_from_ref_cleans_up_after_success(client_strict, engine_db):
    from app.db.session import SessionLocal

    email = f"mat{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Mat"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    create = client_strict.post(
        f"/projects/{project_id}/credential-profiles",
        headers=headers,
        json={
            "name": "Mat GCP",
            "provider": "gcp",
            "credential_type": "gcp_service_account_json",
            "secret": json.dumps(GCP_SA),
        },
    )
    cred_ref = create.json()["credentials_ref"]
    with SessionLocal() as db:
        with profile_svc.materialize_from_ref(
            db,
            credentials_ref=cred_ref,
            provider="gcp",
            project_id=uuid.UUID(project_id),
        ) as materialized:
            assert materialized is not None
            assert materialized.temp_paths == []
            assert "GOOGLE_CREDENTIALS_JSON" in materialized.env


def test_credential_profile_plan_sends_inline_gcp_credentials(
    client_strict, monkeypatch, engine_db, tmp_path
):
    from tests.test_infrastructure_deployments_57e import (
        _create_gcp_deployment,
        _gcp_credentials,
        _install_runner,
        _patch_gcp_ssh_gates,
        _plan_gcp,
        _project_and_topology,
        _register,
    )

    _patch_gcp_ssh_gates(monkeypatch)
    _gcp_credentials(monkeypatch, tmp_path)
    runner = _install_runner(monkeypatch)

    h = _register(client_strict, prefix="credplan")
    _, topo_id = _project_and_topology(client_strict, h)
    project_id = client_strict.get("/projects", headers=h).json()[0]["id"]

    create_profile = client_strict.post(
        f"/projects/{project_id}/credential-profiles",
        headers=h,
        json={
            "name": "Plan GCP",
            "provider": "gcp",
            "credential_type": "gcp_service_account_json",
            "secret": json.dumps(GCP_SA),
        },
    )
    cred_ref = create_profile.json()["credentials_ref"]
    dep_id = _create_gcp_deployment(client_strict, h, topo_id, credentials_ref=cred_ref)

    client_strict.post(f"/infrastructure-deployments/{dep_id}/validate", headers=h)
    _plan_gcp(client_strict, h, dep_id)

    plan_calls = [call for call in runner.calls if call.get("mode") == "plan"]
    assert plan_calls, "expected terraform plan dispatch"
    cred_env = plan_calls[-1]["credentials_env"]
    assert "GOOGLE_CREDENTIALS_JSON" in cred_env
    assert json.loads(cred_env["GOOGLE_CREDENTIALS_JSON"])["client_email"] == GCP_SA["client_email"]
    assert cred_env.get("GOOGLE_APPLICATION_CREDENTIALS", "").startswith("/tmp/cns-gcp-sa-") is False


def test_credential_profile_apply_sends_inline_gcp_credentials(
    client_strict, monkeypatch, engine_db, tmp_path
):
    from tests.test_infrastructure_deployments_57e import (
        _create_gcp_deployment,
        _gcp_credentials,
        _install_runner,
        _patch_gcp_ssh_gates,
        _plan_gcp,
        _project_and_topology,
        _register,
    )

    _patch_gcp_ssh_gates(monkeypatch)
    _gcp_credentials(monkeypatch, tmp_path)
    runner = _install_runner(monkeypatch)

    h = _register(client_strict, prefix="credapply")
    _, topo_id = _project_and_topology(client_strict, h)
    project_id = client_strict.get("/projects", headers=h).json()[0]["id"]

    create_profile = client_strict.post(
        f"/projects/{project_id}/credential-profiles",
        headers=h,
        json={
            "name": "Apply GCP",
            "provider": "gcp",
            "credential_type": "gcp_service_account_json",
            "secret": json.dumps(GCP_SA),
        },
    )
    cred_ref = create_profile.json()["credentials_ref"]
    dep_id = _create_gcp_deployment(client_strict, h, topo_id, credentials_ref=cred_ref)
    _plan_gcp(client_strict, h, dep_id)

    confirm = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True, "confirmation_text": "APPLY"},
    )
    assert confirm.status_code == 200, confirm.text

    apply_calls = [call for call in runner.calls if call.get("mode") == "apply"]
    assert apply_calls, "expected terraform apply dispatch"
    cred_env = apply_calls[-1]["credentials_env"]
    assert "GOOGLE_CREDENTIALS_JSON" in cred_env


def test_infrastructure_deployment_with_credential_profile(client_strict, monkeypatch, engine_db, tmp_path):
    from tests.test_infrastructure_deployments_57e import (
        _create_gcp_deployment,
        _gcp_credentials,
        _install_runner,
        _patch_gcp_ssh_gates,
        _plan_gcp,
        _project_and_topology,
        _register,
    )

    _patch_gcp_ssh_gates(monkeypatch)
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)

    h = _register(client_strict, prefix="credprof")
    _, topo_id = _project_and_topology(client_strict, h)
    project_id = client_strict.get("/projects", headers=h).json()[0]["id"]

    create_profile = client_strict.post(
        f"/projects/{project_id}/credential-profiles",
        headers=h,
        json={
            "name": "Deploy GCP",
            "provider": "gcp",
            "credential_type": "gcp_service_account_json",
            "secret": json.dumps(GCP_SA),
        },
    )
    assert create_profile.status_code == 201, create_profile.text
    cred_ref = create_profile.json()["credentials_ref"]

    dep_id = _create_gcp_deployment(client_strict, h, topo_id, credentials_ref=cred_ref)
    _plan_gcp(client_strict, h, dep_id)

    confirm = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True, "confirmation_text": "APPLY"},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] in {"succeeded", "configuring", "configuration_failed"}


def test_delete_credential_profile(client_strict, engine_db):
    email = f"del{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Del"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    create = client_strict.post(
        f"/projects/{project_id}/credential-profiles",
        headers=headers,
        json={
            "name": "Temp",
            "provider": "gcp",
            "credential_type": "gcp_service_account_json",
            "secret": json.dumps(GCP_SA),
        },
    )
    profile_id = create.json()["id"]
    delete = client_strict.delete(f"/credential-profiles/{profile_id}", headers=headers)
    assert delete.status_code == 204
    gone = client_strict.get(f"/credential-profiles/{profile_id}", headers=headers)
    assert gone.status_code == 404


def test_validate_terraform_credentials_ref_accepts_profile(client_strict, engine_db):
    from app.db.session import SessionLocal

    email = f"val{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Val"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    create = client_strict.post(
        f"/projects/{project_id}/credential-profiles",
        headers=headers,
        json={
            "name": "Valid",
            "provider": "gcp",
            "credential_type": "gcp_service_account_json",
            "secret": json.dumps(GCP_SA),
        },
    )
    cred_ref = create.json()["credentials_ref"]
    with SessionLocal() as db:
        validate_terraform_credentials_ref("gcp", cred_ref, db=db, project_id=uuid.UUID(project_id))
