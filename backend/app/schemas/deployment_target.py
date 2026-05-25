"""Pydantic schemas for deployment targets (Step 57A)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


TARGET_TYPES = frozenset({"remote_docker", "kubernetes", "terraform", "ansible"})
TARGET_STATUSES = frozenset({"active", "disabled"})


class DeploymentTargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    target_type: str = Field(
        pattern="^(remote_docker|kubernetes|terraform|ansible)$",
    )
    config_json: dict = Field(default_factory=dict)
    credentials_ref: str | None = Field(default=None, max_length=255)
    status: str = Field(default="active", pattern="^(active|disabled)$")


class DeploymentTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    target_type: str
    config_json: dict
    credentials_ref: str | None
    status: str
    created_by_user_id: str | None
    created_at: datetime | str


class DeploymentTargetListResponse(BaseModel):
    items: list[DeploymentTargetResponse] = Field(default_factory=list)
