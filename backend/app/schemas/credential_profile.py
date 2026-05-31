"""API schemas for credential profiles (never expose secret material)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CredentialProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=32)
    credential_type: str = Field(min_length=1, max_length=64)
    secret: str = Field(min_length=1, description="Provider secret JSON — never returned by API")
    gcp_project_id: str | None = Field(
        default=None,
        max_length=64,
        description="GCP cloud project ID (required for GCP profiles unless present in service account JSON)",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class CredentialProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    secret: str | None = Field(default=None, min_length=1)
    gcp_project_id: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] | None = None


class CredentialProfileResponse(BaseModel):
    id: str
    project_id: str
    owner_id: str
    name: str
    gcp_project_id: str | None
    provider: str
    credential_type: str
    metadata_json: dict[str, Any]
    validation_status: str
    validation_message: str | None
    last_validated_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime
    credentials_ref: str


class CredentialProfileListResponse(BaseModel):
    items: list[CredentialProfileResponse]


class CredentialProfileValidateResponse(BaseModel):
    id: str
    validation_status: str
    validation_message: str | None
    last_validated_at: datetime | None
