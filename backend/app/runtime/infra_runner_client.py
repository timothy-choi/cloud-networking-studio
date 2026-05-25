"""HTTP client for Go runner infrastructure execution endpoints (Step 57C)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import settings

_log = logging.getLogger(__name__)


@dataclass
class InfraExecutionResult:
    execution_id: str
    status: str
    logs: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None
    error: str | None = None


class InfraRunnerClient(Protocol):
    def run_execution(self, payload: dict[str, Any]) -> InfraExecutionResult: ...


class HttpInfraRunnerClient:
    """Dispatch terraform/ansible jobs to the Go runner."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 900.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base = (base_url or "").strip().rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    @classmethod
    def from_settings(cls) -> HttpInfraRunnerClient:
        return cls(settings.go_runner_url, timeout_seconds=settings.go_runner_timeout_seconds)

    def run_execution(self, payload: dict[str, Any]) -> InfraExecutionResult:
        url = f"{self._base}/infra/executions"
        with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return InfraExecutionResult(
            execution_id=str(data.get("execution_id") or payload.get("execution_id") or ""),
            status=str(data.get("status") or "failed"),
            logs=str(data.get("logs") or ""),
            artifacts=list(data.get("artifacts") or []),
            outputs=dict(data.get("outputs") or {}),
            duration_ms=data.get("duration_ms"),
            error=data.get("error"),
        )


_runner_client: InfraRunnerClient | None = None


def get_infra_runner_client() -> InfraRunnerClient:
    global _runner_client
    if _runner_client is None:
        _runner_client = HttpInfraRunnerClient.from_settings()
    return _runner_client


def set_infra_runner_client(client: InfraRunnerClient | None) -> None:
    global _runner_client
    _runner_client = client
