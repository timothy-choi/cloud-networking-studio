"""HTTP client for the optional Go ``cns-runner`` service."""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.models.deployment import DeploymentEventLevel
from app.services.deployment_planner import DeploymentPlan


class GoRunnerDeployError(Exception):
    """Runner reported a failed deployment (HTTP 4xx or ``status`` != succeeded)."""

    def __init__(self, message: str, events: list[tuple[DeploymentEventLevel, str]]) -> None:
        super().__init__(message)
        self.message = message
        self.events = events


class GoRunnerClient:
    """Thin wrapper over runner REST endpoints used by ``GoHybridDockerRuntimeProvider``."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 600.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        root = (base_url or "").strip().rstrip("/")
        self._base = root
        self._timeout = timeout_seconds
        self._transport = transport

    @classmethod
    def from_settings(cls) -> GoRunnerClient:
        return cls(
            settings.go_runner_url,
            timeout_seconds=settings.go_runner_timeout_seconds,
        )

    def health(self) -> dict[str, Any]:
        with httpx.Client(timeout=min(10.0, self._timeout)) as client:
            r = client.get(f"{self._base}/health")
            r.raise_for_status()
            return r.json()

    def get_runtime_status(self) -> dict[str, Any]:
        """GET ``/runtime/status`` on the runner (short timeout)."""
        timeout = min(10.0, self._timeout)
        kw: dict = {"base_url": self._base, "timeout": httpx.Timeout(timeout)}
        if self._transport is not None:
            kw["transport"] = self._transport
        with httpx.Client(**kw) as client:
            r = client.get("/runtime/status")
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            raise ValueError("runner /runtime/status returned non-object JSON")
        return data

    def _client(self) -> httpx.Client:
        kw: dict = {
            "base_url": self._base,
            "timeout": httpx.Timeout(self._timeout),
        }
        if self._transport is not None:
            kw["transport"] = self._transport
        return httpx.Client(**kw)

    def deployment_request_body(self, plan: DeploymentPlan) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        for n in plan.nodes:
            nodes.append(
                {
                    "id": str(n.id),
                    "name": n.name,
                    "image": n.image,
                    "ip_address": n.ip_address,
                    "node_type": n.node_type,
                }
            )
        plan_links: list[dict[str, Any]] = []
        for pl in plan.plan_links:
            plan_links.append(
                {
                    "link_id": str(pl.link_id),
                    "source_node_id": str(pl.source_node_id),
                    "target_node_id": str(pl.target_node_id),
                    "network_name": pl.network_name,
                    "cidr": pl.cidr,
                    "source_ip": pl.source_ip,
                    "target_ip": pl.target_ip,
                }
            )
        dep_id = plan.deployment_id
        body: dict[str, Any] = {
            "deployment_id": str(dep_id) if dep_id else "",
            "topology_id": str(plan.topology_id),
            "runtime_target": plan.runtime_target,
            "networking_mode": plan.networking_mode,
            "segmented_networks": plan.segmented_networks,
            "nodes": nodes,
            "plan_links": plan_links,
        }
        if plan.project_id:
            body["project_id"] = str(plan.project_id)
        if plan.requested_by_user_id:
            body["requested_by_user_id"] = str(plan.requested_by_user_id)
        if plan.subnet_cidr:
            body["subnet_cidr"] = plan.subnet_cidr
        body["network_allocation_mode"] = plan.network_allocation_mode
        return body

    def post_deployment(
        self, plan: DeploymentPlan
    ) -> tuple[list[tuple[DeploymentEventLevel, str]], dict[str, Any] | None]:
        payload = self.deployment_request_body(plan)
        with self._client() as client:
            r = client.post("/deployments", json=payload)
        return _deployment_response_to_outcome(r)

    def delete_deployment(
        self,
        deployment_id: UUID,
        topology_id: UUID,
        *,
        project_id: UUID | None = None,
    ) -> list[tuple[DeploymentEventLevel, str]]:
        params: dict[str, str] = {"topology_id": str(topology_id)}
        if project_id is not None:
            params["project_id"] = str(project_id)
        with self._client() as client:
            r = client.delete(
                f"/deployments/{deployment_id}",
                params=params,
            )
        data = _safe_json(r)
        events = _events_from_runner_payload(data.get("events"))
        if r.is_success:
            return events
        msg = str(data.get("error") or r.text or r.reason_phrase)
        raise RuntimeError(f"go runner destroy failed ({r.status_code}): {msg}")

    def get_deployment_logs(
        self,
        deployment_id: UUID,
        topology_id: UUID,
        node_id: UUID,
        tail: int,
        *,
        project_id: UUID | None = None,
    ) -> str | None:
        params: dict[str, str] = {
            "topology_id": str(topology_id),
            "node_id": str(node_id),
            "tail": str(tail),
        }
        if project_id is not None:
            params["project_id"] = str(project_id)
        with self._client() as client:
            r = client.get(
                f"/deployments/{deployment_id}/logs",
                params=params,
            )
        data = _safe_json(r)
        if r.status_code == 404:
            return None
        if not r.is_success:
            return None
        err = data.get("error")
        if err:
            return None
        logs = data.get("logs")
        return str(logs) if logs is not None else None

    def post_traffic_test(self, body: dict[str, Any]) -> dict[str, Any]:
        with self._client() as client:
            r = client.post("/traffic-tests", json=body)
        data = _safe_json(r)
        if not r.is_success and not isinstance(data, dict):
            raise RuntimeError(f"go runner traffic-test failed: {r.status_code} {r.text}")
        return data

    def get_runtime_deployment_logs(
        self,
        deployment_id: UUID,
        topology_id: UUID,
        *,
        tail: int,
        project_id: UUID | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {
            "topology_id": str(topology_id),
            "tail": str(int(tail)),
        }
        if project_id is not None:
            params["project_id"] = str(project_id)
        with self._client() as client:
            r = client.get(f"/deployments/{deployment_id}/runtime/logs", params=params)
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, dict):
            raise ValueError("runner returned non-object JSON for runtime logs")
        return raw

    def get_runtime_service_logs(
        self,
        deployment_id: UUID,
        topology_id: UUID,
        workload_node_id: str,
        *,
        tail: int,
        project_id: UUID | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"topology_id": str(topology_id), "tail": str(int(tail))}
        if project_id is not None:
            params["project_id"] = str(project_id)
        with self._client() as client:
            r = client.get(
                f"/deployments/{deployment_id}/runtime/services/{workload_node_id}/logs",
                params=params,
            )
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, dict):
            raise ValueError("runner returned non-object JSON for service logs")
        return raw

    def post_runtime_service_health(
        self,
        deployment_id: UUID,
        topology_id: UUID,
        workload_node_id: str,
        *,
        project_id: UUID | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"topology_id": str(topology_id)}
        if project_id is not None:
            params["project_id"] = str(project_id)
        with self._client() as client:
            r = client.post(
                f"/deployments/{deployment_id}/runtime/services/{workload_node_id}/health-check",
                params=params,
                json=body or {},
            )
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, dict):
            raise ValueError("runner returned non-object JSON for health check")
        return raw

    def post_runtime_traffic_test(self, deployment_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        with self._client() as client:
            r = client.post(f"/deployments/{deployment_id}/runtime/traffic-tests", json=body)
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, dict):
            raise ValueError("runner returned non-object JSON for traffic test")
        return raw

    def post_runtime_service_exec(
        self,
        deployment_id: UUID,
        topology_id: UUID,
        workload_node_id: str,
        body: dict[str, Any],
        *,
        project_id: UUID | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"topology_id": str(topology_id)}
        if project_id is not None:
            params["project_id"] = str(project_id)
        with self._client() as client:
            r = client.post(
                f"/deployments/{deployment_id}/runtime/services/{workload_node_id}/exec",
                params=params,
                json=body,
            )
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, dict):
            raise ValueError("runner returned non-object JSON for exec")
        return raw

    def post_runtime_service_restart(
        self,
        deployment_id: UUID,
        topology_id: UUID,
        workload_node_id: str,
        *,
        project_id: UUID | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"topology_id": str(topology_id)}
        if project_id is not None:
            params["project_id"] = str(project_id)
        with self._client() as client:
            r = client.post(
                f"/deployments/{deployment_id}/runtime/services/{workload_node_id}/restart",
                params=params,
            )
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, dict):
            raise ValueError("runner returned non-object JSON for restart")
        return raw


def _safe_json(r: httpx.Response) -> dict[str, Any]:
    try:
        out = r.json()
        return out if isinstance(out, dict) else {}
    except ValueError:
        return {}


def _level_from_runner(level: str) -> DeploymentEventLevel:
    key = (level or "").strip().lower()
    mapping = {
        "debug": DeploymentEventLevel.DEBUG,
        "info": DeploymentEventLevel.INFO,
        "warning": DeploymentEventLevel.WARNING,
        "error": DeploymentEventLevel.ERROR,
    }
    return mapping.get(key, DeploymentEventLevel.INFO)


def _events_from_runner_payload(raw: Any) -> list[tuple[DeploymentEventLevel, str]]:
    if not isinstance(raw, list):
        return []
    out: list[tuple[DeploymentEventLevel, str]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        msg = str(row.get("message") or "")
        out.append((_level_from_runner(str(row.get("level") or "info")), msg))
    return out


def _extract_runtime_access_from_response(data: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize runner deploy JSON into a persistence-ready ``runtime_access`` dict."""
    ra = data.get("runtime_access")
    if ra is None:
        legacy = data.get("runtime_resources")
        if isinstance(legacy, dict):
            ra = legacy
    if not isinstance(ra, dict):
        return None
    out: dict[str, Any] = dict(ra)
    if not str(out.get("runtime_provider") or "").strip():
        rp = data.get("runtime_provider")
        if rp is not None and str(rp).strip():
            out["runtime_provider"] = str(rp).strip()
    if out.get("resources") is None:
        out["resources"] = []
    return out


def _deployment_response_to_outcome(
    r: httpx.Response,
) -> tuple[list[tuple[DeploymentEventLevel, str]], dict[str, Any] | None]:
    data = _safe_json(r)
    events = _events_from_runner_payload(data.get("events"))
    status = str(data.get("status") or "").lower()
    err = data.get("error")
    err_s = str(err).strip() if err else ""

    if r.is_success and status in ("succeeded", "success") and not err_s:
        return events, _extract_runtime_access_from_response(data)

    if not err_s:
        err_s = f"runner returned status={status or 'unknown'} (http {r.status_code})"
    raise GoRunnerDeployError(err_s, events)


def effective_runtime_executor() -> str:
    """
    Executor mode: prefer ``RUNTIME_EXECUTOR`` from the process environment (Docker / Compose),
    then fall back to ``settings`` so delegation matches what the container actually sees.
    """
    raw = os.environ.get("RUNTIME_EXECUTOR")
    if raw is not None and str(raw).strip() != "":
        return str(raw).strip().lower()
    return (settings.runtime_executor or "python").strip().lower()


def use_go_runner_for_docker() -> bool:
    """True when the control plane should delegate Docker deploy/destroy to the Go runner."""
    if os.environ.get("CNS_USE_FAKE_DOCKER", "").lower() in ("1", "true", "yes"):
        return False
    return effective_runtime_executor() == "go"
