"""HTTP client for Go runner infrastructure execution endpoints (Step 57C)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.services.infra_security import redact_logs
from app.services.terraform_credentials_service import redact_credentials_env

_log = logging.getLogger(__name__)

# Runner returns 422 when an infra job completes with status=failed (not a transport error).
_RUNNER_EXECUTION_RESPONSE_CODES = frozenset({200, 422})


@dataclass
class InfraExecutionResult:
    execution_id: str
    status: str
    logs: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None
    error: str | None = None
    http_status: int | None = None


class InfraRunnerClientError(Exception):
    """Runner HTTP transport failure (connection error or unexpected status)."""

    def __init__(self, message: str, *, status_code: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class InfraRunnerClient(Protocol):
    def run_execution(self, payload: dict[str, Any]) -> InfraExecutionResult: ...


def _sanitize_payload_for_log(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    if cred_env := out.get("credentials_env"):
        if isinstance(cred_env, dict):
            out["credentials_env"] = redact_credentials_env(cred_env)
    return out


def _parse_execution_response(data: dict[str, Any], *, payload: dict[str, Any], http_status: int) -> InfraExecutionResult:
    error_raw = data.get("error")
    error_text = str(error_raw).strip() if error_raw else None
    logs = redact_logs(str(data.get("logs") or ""))
    if error_text:
        error_text = redact_logs(error_text)
    return InfraExecutionResult(
        execution_id=str(data.get("execution_id") or payload.get("execution_id") or ""),
        status=str(data.get("status") or "failed"),
        logs=logs,
        artifacts=list(data.get("artifacts") or []),
        outputs=dict(data.get("outputs") or {}),
        duration_ms=data.get("duration_ms"),
        error=error_text,
        http_status=http_status,
    )


def _runner_failure_detail(data: dict[str, Any]) -> str:
    error_raw = data.get("error")
    if error_raw:
        return redact_logs(str(error_raw))
    logs = redact_logs(str(data.get("logs") or ""))
    if logs.strip():
        tail = logs.strip()[-500:]
        return tail
    return "Infrastructure runner execution failed"


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
        safe_payload = _sanitize_payload_for_log(payload)
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                resp = client.post(url, json=payload)
        except httpx.RequestError as exc:
            _log.error("infra runner request failed mode=%s: %s", payload.get("mode"), exc)
            raise InfraRunnerClientError(f"Infrastructure runner unavailable: {exc}") from exc

        if resp.status_code in _RUNNER_EXECUTION_RESPONSE_CODES:
            try:
                data = resp.json()
            except ValueError as exc:
                _log.error(
                    "infra runner returned non-JSON body status=%s mode=%s",
                    resp.status_code,
                    payload.get("mode"),
                )
                raise InfraRunnerClientError(
                    "Infrastructure runner returned an invalid response",
                    status_code=resp.status_code,
                    detail=redact_logs(resp.text[:2000]),
                ) from exc
            if not isinstance(data, dict):
                raise InfraRunnerClientError(
                    "Infrastructure runner returned an invalid response",
                    status_code=resp.status_code,
                )
            result = _parse_execution_response(data, payload=payload, http_status=resp.status_code)
            if resp.status_code == 422 or result.status != "succeeded":
                _log.warning(
                    "infra runner execution failed status=%s mode=%s execution_type=%s error=%s payload=%s",
                    resp.status_code,
                    payload.get("mode"),
                    payload.get("execution_type"),
                    result.error or _runner_failure_detail(data),
                    safe_payload,
                )
            return result

        detail = redact_logs(resp.text[:2000])
        _log.error(
            "infra runner unexpected HTTP status=%s mode=%s detail=%s payload=%s",
            resp.status_code,
            payload.get("mode"),
            detail,
            safe_payload,
        )
        raise InfraRunnerClientError(
            f"Infrastructure runner error (HTTP {resp.status_code})",
            status_code=resp.status_code,
            detail=detail,
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
