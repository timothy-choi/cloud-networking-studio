"""Resolve credentials_ref for Terraform cloud providers (Step 57D)."""

from __future__ import annotations

import json
import os
import re

_GCP_REFS = frozenset({"env:GOOGLE_APPLICATION_CREDENTIALS", "env:GOOGLE_CREDENTIALS_JSON"})
_AWS_PROFILE_REFS = frozenset({"env:AWS_PROFILE"})
_AWS_KEY_PAIR = ("env:AWS_ACCESS_KEY_ID", "env:AWS_SECRET_ACCESS_KEY")

_ENV_REF = re.compile(r"^env:([A-Z0-9_]{1,64})$")


def _redact_env_value(key: str) -> str:
    upper = key.upper()
    if "SECRET" in upper or "CREDENTIAL" in upper or "KEY" in upper or "TOKEN" in upper:
        return "<redacted>"
    return "<set>"


def resolve_terraform_credentials_env(provider: str, credentials_ref: str | None) -> dict[str, str]:
    """
    Resolve credentials_ref to environment variables for the runner process.

    Never returns secret values in logs — callers must redact before persisting.
    """
    ref = (credentials_ref or "").strip()
    if not ref:
        raise ValueError("Terraform credentials_ref is not configured on the server.")

    provider_key = provider.strip().lower()
    if provider_key == "gcp":
        return _resolve_gcp(ref)
    if provider_key == "aws":
        return _resolve_aws(ref)

    raise ValueError(f"Terraform credentials_ref is not supported for provider '{provider}'.")


def describe_credentials_ref(credentials_ref: str | None) -> str:
    """Safe description for logs/UI (no secret material)."""
    ref = (credentials_ref or "").strip()
    if not ref:
        return "not configured"
    if ref.startswith("env:"):
        var_name = ref[4:]
        return f"env:{var_name} ({_redact_env_value(var_name)})"
    return ref


def _resolve_gcp(ref: str) -> dict[str, str]:
    if ref not in _GCP_REFS:
        raise ValueError(
            "GCP credentials_ref must be env:GOOGLE_APPLICATION_CREDENTIALS or env:GOOGLE_CREDENTIALS_JSON."
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

    # GOOGLE_CREDENTIALS_JSON — validate JSON without logging content
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
        "AWS credentials_ref must be env:AWS_PROFILE or env:AWS_ACCESS_KEY_ID (with AWS_SECRET_ACCESS_KEY set)."
    )


def redact_credentials_env(env: dict[str, str]) -> dict[str, str]:
    return {k: _redact_env_value(k) for k in env}
