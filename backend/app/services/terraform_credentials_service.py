"""Resolve credentials_ref for Terraform cloud providers (Step 57D + credential profiles)."""

from __future__ import annotations

import json
import os
import re
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.credential_profile_service import (
    CREDENTIAL_REF_PREFIX,
    materialize_from_ref,
    parse_credential_profile_ref,
)

_GCP_REFS = frozenset({"env:GOOGLE_APPLICATION_CREDENTIALS", "env:GOOGLE_CREDENTIALS_JSON"})
_AWS_PROFILE_REFS = frozenset({"env:AWS_PROFILE"})
_ENV_REF = re.compile(r"^env:([A-Z0-9_]{1,64})$")


def _redact_env_value(key: str) -> str:
    upper = key.upper()
    if "SECRET" in upper or "CREDENTIAL" in upper or "KEY" in upper or "TOKEN" in upper:
        return "<redacted>"
    return "<set>"


def is_credential_profile_ref(credentials_ref: str | None) -> bool:
    return (credentials_ref or "").strip().startswith(CREDENTIAL_REF_PREFIX)


def resolve_terraform_credentials_env(
    provider: str,
    credentials_ref: str | None,
    *,
    db: Session | None = None,
    project_id: UUID | None = None,
) -> dict[str, str]:
    """
    Resolve credentials_ref to environment variables for the runner process.

    For credential:<profile_id> refs, db and project_id are required. Caller must
    run cleanup via materialize_from_ref when executing Terraform.
    """
    ref = (credentials_ref or "").strip()
    if not ref:
        raise ValueError("Terraform credentials_ref is not configured on the server.")

    if is_credential_profile_ref(ref):
        if db is None or project_id is None:
            raise ValueError("Credential profile reference requires an active deployment context.")
        parse_credential_profile_ref(ref)
        raise ValueError(
            "Credential profile references must be resolved via materialize_from_ref during Terraform execution."
        )

    provider_key = provider.strip().lower()
    if provider_key == "gcp":
        return _resolve_gcp(ref)
    if provider_key == "aws":
        return _resolve_aws(ref)
    if provider_key == "azure":
        raise ValueError(
            "Azure Terraform requires credentials_ref credential:<profile_id> (stored credential profile)."
        )

    raise ValueError(f"Terraform credentials_ref is not supported for provider '{provider}'.")


def resolve_terraform_credentials_env_materialized(
    provider: str,
    credentials_ref: str | None,
    *,
    db: Session,
    project_id: UUID,
) -> dict[str, str]:
    """Resolve env vars, including credential profiles (caller manages cleanup separately)."""
    ref = (credentials_ref or "").strip()
    if not ref:
        raise ValueError("Terraform credentials_ref is not configured on the server.")

    if is_credential_profile_ref(ref):
        with materialize_from_ref(db, credentials_ref=ref, provider=provider, project_id=project_id) as mat:
            if mat is None:
                raise ValueError("Credential profile materialization failed.")
            return dict(mat.env)
        return {}

    return resolve_terraform_credentials_env(provider, ref)


def validate_terraform_credentials_ref(
    provider: str,
    credentials_ref: str | None,
    *,
    db: Session | None = None,
    project_id: UUID | None = None,
) -> None:
    """Validate that credentials_ref can be resolved without materializing secrets."""
    ref = (credentials_ref or "").strip()
    if not ref:
        raise ValueError("Terraform credentials_ref is not configured on the server.")

    if is_credential_profile_ref(ref):
        if db is None or project_id is None:
            raise ValueError("Credential profile reference requires project context.")
        from app.services.credential_profile_service import (
            assert_profile_usable_for_provider,
            get_profile_for_project,
        )

        profile_id = parse_credential_profile_ref(ref)
        profile = get_profile_for_project(db, profile_id=profile_id, project_id=project_id)
        if profile is None:
            raise ValueError("Credential profile not found for this project.")
        assert_profile_usable_for_provider(profile, provider)
        return

    resolve_terraform_credentials_env(provider, ref)


def describe_credentials_ref(credentials_ref: str | None) -> str:
    """Safe description for logs/UI (no secret material)."""
    ref = (credentials_ref or "").strip()
    if not ref:
        return "not configured"
    if ref.startswith(CREDENTIAL_REF_PREFIX):
        return f"{ref} (<stored profile>)"
    if ref.startswith("env:"):
        var_name = ref[4:]
        return f"env:{var_name} ({_redact_env_value(var_name)})"
    return ref


def _resolve_gcp(ref: str) -> dict[str, str]:
    if ref not in _GCP_REFS:
        raise ValueError(
            "GCP credentials_ref must be env:GOOGLE_APPLICATION_CREDENTIALS, "
            "env:GOOGLE_CREDENTIALS_JSON, or credential:<profile_id>."
        )
    var_name = ref[4:]
    raw = (os.environ.get(var_name) or "").strip()
    if not raw:
        raise ValueError("Terraform credentials_ref is not configured on the server.")

    if var_name == "GOOGLE_APPLICATION_CREDENTIALS":
        if not os.path.isfile(raw):
            raise ValueError("Terraform credentials_ref is not configured on the server.")
        if not os.access(raw, os.R_OK):
            raise ValueError("Terraform credentials_ref is not configured on the server.")
        return {"GOOGLE_APPLICATION_CREDENTIALS": raw}

    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Terraform credentials_ref is not configured on the server.") from exc
    return {"GOOGLE_CREDENTIALS_JSON": raw}


def _resolve_aws(ref: str) -> dict[str, str]:
    if ref in _AWS_PROFILE_REFS:
        var_name = ref[4:]
        profile = (os.environ.get(var_name) or "").strip()
        if not profile:
            raise ValueError("Terraform credentials_ref is not configured on the server.")
        return {"AWS_PROFILE": profile}

    if ref == "env:AWS_ACCESS_KEY_ID":
        key_id = (os.environ.get("AWS_ACCESS_KEY_ID") or "").strip()
        secret = (os.environ.get("AWS_SECRET_ACCESS_KEY") or "").strip()
        if not key_id or not secret:
            raise ValueError("Terraform credentials_ref is not configured on the server.")
        region = (os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "").strip()
        env = {"AWS_ACCESS_KEY_ID": key_id, "AWS_SECRET_ACCESS_KEY": secret}
        if region:
            env["AWS_DEFAULT_REGION"] = region
        return env

    match = _ENV_REF.match(ref)
    if match and ref.endswith("AWS_ACCESS_KEY_ID"):
        return _resolve_aws("env:AWS_ACCESS_KEY_ID")

    raise ValueError(
        "AWS credentials_ref must be env:AWS_PROFILE, env:AWS_ACCESS_KEY_ID "
        "(with AWS_SECRET_ACCESS_KEY set), or credential:<profile_id>."
    )


def redact_credentials_env(env: dict[str, str]) -> dict[str, str]:
    return {k: _redact_env_value(k) for k in env}
