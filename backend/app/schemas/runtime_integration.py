"""Integration snippets and topology→runtime mapping for Step 49."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class IntegrationSnippet(BaseModel):
    id: str
    title: str
    language: str
    content: str


class RuntimeMappingRow(BaseModel):
    topology_node_id: UUID | None = None
    topology_node_name: str | None = None
    resource_id: UUID | None = None
    resource_type: str | None = None
    runtime_name: str | None = None
    container_id: str | None = None
    pod_name: str | None = None
    internal_url: str | None = None
    external_url: str | None = None
    namespace_or_network: str | None = None
    status: str | None = None


class DeploymentIntegrationResponse(BaseModel):
    deployment_id: UUID
    topology_id: UUID
    runtime_provider: str
    namespace_or_network: str | None = None
    internal_endpoints: list[dict[str, Any]] = Field(default_factory=list)
    exposed_endpoints: list[dict[str, Any]] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)
    connect_your_app: dict[str, Any] = Field(default_factory=dict)
    snippets: list[IntegrationSnippet] = Field(default_factory=list)
    instructions: dict[str, Any] = Field(default_factory=dict)


class DeploymentRuntimeMappingResponse(BaseModel):
    deployment_id: UUID
    topology_id: UUID
    runtime_provider: str
    rows: list[RuntimeMappingRow] = Field(default_factory=list)
