"""Step 51A: integration outputs for use outside CNS."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class IntegrationServiceOutput(BaseModel):
    name: str
    runtime_name: str | None = None
    internal_url: str | None = None
    external_url: str | None = None
    preferred_url: str | None = None
    endpoint_scope: str = Field(
        description="external when a public/exposed URL is preferred; internal_only otherwise"
    )
    url_note: str | None = None
    protocol: str | None = None
    port: int | None = None
    recommended_env_var: str
    env_vars: dict[str, str] = Field(default_factory=dict)


class IntegrationOutputsBundle(BaseModel):
    env: str = ""
    curl: str = ""
    bash: str = ""
    python: str = ""
    javascript: str = ""
    typescript: str = ""
    java: str = ""
    go: str = ""
    ruby: str = ""
    php: str = ""
    csharp: str = ""
    github_actions: str = ""
    docker_compose_env: str = ""
    kubernetes_configmap: str = ""


class DeploymentIntegrationOutputsResponse(BaseModel):
    deployment_id: UUID
    topology_id: UUID
    runtime_provider: str
    namespace_or_network: str | None = None
    services: list[IntegrationServiceOutput] = Field(default_factory=list)
    outputs: IntegrationOutputsBundle = Field(default_factory=IntegrationOutputsBundle)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntegrationOutputFileItem(BaseModel):
    name: str
    type: str
    download_url: str
