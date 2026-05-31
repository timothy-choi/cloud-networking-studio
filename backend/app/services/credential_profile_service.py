"""Credential profile CRUD, validation, and Terraform materialization."""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.credential_encryption import decrypt_secret, encrypt_secret
from app.core.secret_masking import scrub_sensitive_dict
from app.models.credential_profile import CredentialProfile
from app.models.user import User
from app.services.audit_service import record_audit

SUPPORTED_PROVIDERS = frozenset({"gcp", "aws", "azure"})
CREDENTIAL_REF_PREFIX = "credential:"

GCP_TYPES = frozenset({"gcp_service_account_json"})
AWS_TYPES = frozenset({"aws_access_key"})
AZURE_TYPES = frozenset({"azure_service_principal"})

_PROVIDER_TYPES: dict[str, frozenset[str]] = {
    "gcp": GCP_TYPES,
    "aws": AWS_TYPES,
    "azure": AZURE_TYPES,
}


def credentials_ref_for_profile(profile_id: UUID) -> str:
    return f"{CREDENTIAL_REF_PREFIX}{profile_id}"


def parse_credential_profile_ref(credentials_ref: str | None) -> UUID | None:
    ref = (credentials_ref or "").strip()
    if not ref.startswith(CREDENTIAL_REF_PREFIX):
        return None
    raw = ref[len(CREDENTIAL_REF_PREFIX) :].strip()
    try:
        return UUID(raw)
    except ValueError:
        raise ValueError("Invalid credential profile reference.") from None


def list_profiles(db: Session, project_id: UUID) -> list[CredentialProfile]:
    return list(
        db.scalars(
            select(CredentialProfile)
            .where(CredentialProfile.project_id == project_id)
            .order_by(CredentialProfile.name.asc())
        ).all()
    )


def get_profile(db: Session, profile_id: UUID) -> CredentialProfile | None:
    return db.get(CredentialProfile, profile_id)


def get_profile_for_project(
    db: Session, *, profile_id: UUID, project_id: UUID
) -> CredentialProfile | None:
    return db.scalar(
        select(CredentialProfile).where(
            CredentialProfile.id == profile_id,
            CredentialProfile.project_id == project_id,
        )
    )


def _normalize_provider(provider: str) -> str:
    key = provider.strip().lower()
    if key not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider '{provider}'. Use gcp, aws, or azure.")
    return key


def _validate_secret_structure(
    *,
    provider: str,
    credential_type: str,
    secret: str,
    metadata: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    provider_key = _normalize_provider(provider)
    allowed = _PROVIDER_TYPES.get(provider_key, frozenset())
    if credential_type not in allowed:
        raise ValueError(
            f"Unsupported credential_type '{credential_type}' for provider '{provider_key}'."
        )

    try:
        payload = json.loads(secret)
    except json.JSONDecodeError as exc:
        raise ValueError("Secret must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Secret JSON must be an object.")

    meta = dict(metadata or {})

    if provider_key == "gcp" and credential_type == "gcp_service_account_json":
        for key in ("type", "project_id", "private_key", "client_email"):
            if not str(payload.get(key) or "").strip():
                raise ValueError(f"GCP service account JSON missing required field '{key}'.")
        if payload.get("type") != "service_account":
            raise ValueError("GCP credential must be a service account JSON (type=service_account).")
        return provider_key, meta

    if provider_key == "aws" and credential_type == "aws_access_key":
        if not str(payload.get("access_key_id") or "").strip():
            raise ValueError("AWS credential JSON missing access_key_id.")
        if not str(payload.get("secret_access_key") or "").strip():
            raise ValueError("AWS credential JSON missing secret_access_key.")
        region = str(payload.get("region") or meta.get("region") or "").strip()
        if region:
            meta["region"] = region
        return provider_key, meta

    if provider_key == "azure" and credential_type == "azure_service_principal":
        for key in ("client_id", "client_secret", "tenant_id", "subscription_id"):
            value = str(payload.get(key) or meta.get(key) or "").strip()
            if not value:
                raise ValueError(f"Azure credential missing required field '{key}'.")
            meta[key] = value
        return provider_key, meta

    raise ValueError("Unsupported credential profile configuration.")


def create_profile(
    db: Session,
    *,
    project_id: UUID,
    actor: User,
    name: str,
    provider: str,
    credential_type: str,
    secret: str,
    metadata: dict[str, Any] | None = None,
) -> CredentialProfile:
    provider_key, meta = _validate_secret_structure(
        provider=provider,
        credential_type=credential_type,
        secret=secret,
        metadata=metadata or {},
    )
    profile = CredentialProfile(
        project_id=project_id,
        owner_id=actor.id,
        name=name.strip(),
        provider=provider_key,
        credential_type=credential_type,
        encrypted_secret=encrypt_secret(secret),
        metadata_json=meta,
        validation_status="pending",
        validation_message=None,
    )
    db.add(profile)
    db.flush()
    validate_profile(db, profile=profile, actor=actor, record_audit_event=False)
    record_audit(
        db,
        action="credential_profile.created",
        resource_type="credential_profile",
        resource_id=profile.id,
        project_id=project_id,
        actor_user_id=actor.id,
        metadata=scrub_sensitive_dict(
            {
                "provider": profile.provider,
                "credential_type": profile.credential_type,
            }
        ),
    )
    return profile


def update_profile(
    db: Session,
    *,
    profile: CredentialProfile,
    actor: User,
    name: str | None = None,
    secret: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CredentialProfile:
    if name is not None:
        profile.name = name.strip()
    if secret is not None:
        provider_key, meta = _validate_secret_structure(
            provider=profile.provider,
            credential_type=profile.credential_type,
            secret=secret,
            metadata=metadata if metadata is not None else profile.metadata_json,
        )
        profile.encrypted_secret = encrypt_secret(secret)
        profile.metadata_json = meta
        profile.validation_status = "pending"
        profile.validation_message = None
    elif metadata is not None:
        _, meta = _validate_secret_structure(
            provider=profile.provider,
            credential_type=profile.credential_type,
            secret=decrypt_secret(profile.encrypted_secret),
            metadata=metadata,
        )
        profile.metadata_json = meta

    db.flush()
    if secret is not None:
        validate_profile(db, profile=profile, actor=actor, record_audit_event=False)

    record_audit(
        db,
        action="credential_profile.updated",
        resource_type="credential_profile",
        resource_id=profile.id,
        project_id=profile.project_id,
        actor_user_id=actor.id,
        metadata=scrub_sensitive_dict({"rotated_secret": secret is not None}),
    )
    return profile


def delete_profile(
    db: Session,
    *,
    profile: CredentialProfile,
    actor: User,
) -> None:
    pid = profile.id
    project_id = profile.project_id
    db.delete(profile)
    db.flush()
    record_audit(
        db,
        action="credential_profile.deleted",
        resource_type="credential_profile",
        resource_id=pid,
        project_id=project_id,
        actor_user_id=actor.id,
    )


def validate_profile(
    db: Session,
    *,
    profile: CredentialProfile,
    actor: User,
    record_audit_event: bool = True,
) -> CredentialProfile:
    try:
        secret = decrypt_secret(profile.encrypted_secret)
        _validate_secret_structure(
            provider=profile.provider,
            credential_type=profile.credential_type,
            secret=secret,
            metadata=profile.metadata_json or {},
        )
        profile.validation_status = "valid"
        profile.validation_message = "Credential structure validated."
    except ValueError as exc:
        profile.validation_status = "invalid"
        profile.validation_message = str(exc)
    profile.last_validated_at = datetime.now(UTC)
    db.flush()
    if record_audit_event:
        record_audit(
            db,
            action="credential_profile.validated",
            resource_type="credential_profile",
            resource_id=profile.id,
            project_id=profile.project_id,
            actor_user_id=actor.id,
            status=profile.validation_status,
            metadata=scrub_sensitive_dict({"validation_status": profile.validation_status}),
        )
    return profile


def assert_profile_usable_for_provider(profile: CredentialProfile, provider: str) -> None:
    if profile.validation_status != "valid":
        raise ValueError(
            f"Credential profile '{profile.name}' is not validated "
            f"(status={profile.validation_status})."
        )
    if profile.provider != provider.strip().lower():
        raise ValueError(
            f"Credential profile provider '{profile.provider}' does not match deployment provider '{provider}'."
        )


def mark_profile_used(db: Session, *, profile: CredentialProfile) -> None:
    profile.last_used_at = datetime.now(UTC)
    db.flush()


@dataclass
class MaterializedCredentials:
    env: dict[str, str] = field(default_factory=dict)
    temp_paths: list[str] = field(default_factory=list)

    def cleanup(self) -> None:
        for path in self.temp_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        self.temp_paths.clear()


def materialize_profile_credentials(profile: CredentialProfile) -> MaterializedCredentials:
    secret = decrypt_secret(profile.encrypted_secret)
    payload = json.loads(secret)
    meta = profile.metadata_json or {}
    materialized = MaterializedCredentials()

    if profile.provider == "gcp":
        fd, path = tempfile.mkstemp(prefix="cns-gcp-sa-", suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.chmod(path, 0o600)
        materialized.env["GOOGLE_APPLICATION_CREDENTIALS"] = path
        materialized.temp_paths.append(path)
        return materialized

    if profile.provider == "aws":
        materialized.env["AWS_ACCESS_KEY_ID"] = str(payload["access_key_id"]).strip()
        materialized.env["AWS_SECRET_ACCESS_KEY"] = str(payload["secret_access_key"]).strip()
        region = str(payload.get("region") or meta.get("region") or "").strip()
        if region:
            materialized.env["AWS_DEFAULT_REGION"] = region
        return materialized

    if profile.provider == "azure":
        materialized.env["ARM_CLIENT_ID"] = str(meta.get("client_id") or payload.get("client_id")).strip()
        materialized.env["ARM_CLIENT_SECRET"] = str(
            payload.get("client_secret") or meta.get("client_secret")
        ).strip()
        materialized.env["ARM_TENANT_ID"] = str(meta.get("tenant_id") or payload.get("tenant_id")).strip()
        materialized.env["ARM_SUBSCRIPTION_ID"] = str(
            meta.get("subscription_id") or payload.get("subscription_id")
        ).strip()
        return materialized

    raise ValueError(f"Unsupported credential profile provider '{profile.provider}'.")


@contextmanager
def materialize_from_ref(
    db: Session,
    *,
    credentials_ref: str,
    provider: str,
    project_id: UUID,
) -> Iterator[MaterializedCredentials | None]:
    profile_id = parse_credential_profile_ref(credentials_ref)
    if profile_id is None:
        yield None
        return

    profile = get_profile_for_project(db, profile_id=profile_id, project_id=project_id)
    if profile is None:
        raise ValueError("Credential profile not found for this project.")

    assert_profile_usable_for_provider(profile, provider)
    materialized = materialize_profile_credentials(profile)
    mark_profile_used(db, profile=profile)
    record_audit(
        db,
        action="credential_profile.used",
        resource_type="credential_profile",
        resource_id=profile.id,
        project_id=project_id,
        actor_user_id=profile.owner_id,
        metadata=scrub_sensitive_dict({"provider": profile.provider}),
    )
    try:
        yield materialized
    finally:
        materialized.cleanup()
