"""Pydantic schemas for deployment profiles (Step 56)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeploymentProfileConfig(BaseModel):
    env_overrides: dict[str, dict[str, str]] = Field(default_factory=dict)
    image_tag_overrides: dict[str, str] = Field(default_factory=dict)
    replica_hints: dict[str, Any] = Field(default_factory=dict)
    expose_policy: str | None = Field(default=None, description="restricted|open")
    health_check_strictness: str | None = Field(default=None, description="relaxed|strict")
    runtime_provider_preference: str | None = None
    debug_toolbox_enabled: bool | None = None
    ttl_hours: int | None = None
    cleanup_policy: str | None = None
    quota_limits: dict[str, Any] = Field(default_factory=dict)
    resource_limits: dict[str, Any] = Field(default_factory=dict)


class DeploymentProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    profile_type: str = Field(default="custom", pattern="^(dev|staging|prod_like|custom)$")
    config_json: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class DeploymentProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    profile_type: str | None = Field(default=None, pattern="^(dev|staging|prod_like|custom)$")
    config_json: dict[str, Any] | None = None


class DeploymentProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topology_id: UUID
    name: str
    description: str | None
    profile_type: str
    config_json: dict[str, Any]
    is_default: bool
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class DeploymentProfileListResponse(BaseModel):
    items: list[DeploymentProfileResponse]
