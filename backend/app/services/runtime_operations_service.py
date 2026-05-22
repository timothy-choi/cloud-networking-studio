"""Runtime operations (logs, health checks, traffic tests) — Go runner or Python provider fallback."""

from __future__ import annotations

import logging
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.topology import Topology, TopologyNode
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.runtime import go_runner_client as grc
from app.schemas.runtime import (
    RuntimeOperationsHealthResponse,
    RuntimeOperationsLogsResponse,
    RuntimeOperationsTrafficRequest,
    RuntimeOperationsTrafficResponse,
)
from app.services.deployment_runtime_resource_service import list_runtime_resources
from app.services.node_runtime_config import (
    extract_node_runtime_config,
    health_probe_payload_for_node,
)

_log = logging.getLogger(__name__)

def _runner_client() -> grc.GoRunnerClient:
    return grc.GoRunnerClient.from_settings()


def workload_node_id(row: DeploymentRuntimeResource) -> UUID | None:
    if row.service_id is not None:
        return row.service_id
    return row.node_id


def get_runtime_resource_row(
    db: Session, deployment_id: UUID, resource_id: UUID
) -> DeploymentRuntimeResource:
    row = db.get(DeploymentRuntimeResource, resource_id)
    if row is None or row.deployment_id != deployment_id:
        raise ValueError("runtime resource not found")
    return row


def fetch_runtime_deployment_logs(
    db: Session, deployment_id: UUID, tail: int = 100
) -> RuntimeOperationsLogsResponse:
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    tail = max(1, min(int(tail or 100), 5000))
    prov_name = (dep.runtime_target or "docker").strip() or "docker"

    if grc.should_delegate_runtime_ops_to_go_runner():
        grc.log_runtime_op_delegation("logs", deployment_id)
        data = _runner_client().get_runtime_deployment_logs(
            deployment_id,
            dep.topology_id,
            tail=tail,
            project_id=topo.project_id,
        )
        return RuntimeOperationsLogsResponse(
            deployment_id=deployment_id,
            service_id=data.get("service_id"),
            logs=str(data.get("logs") or ""),
            items=list(data.get("items") or []) if isinstance(data.get("items"), list) else [],
            runtime_provider=str(data.get("runtime_provider") or prov_name),
        )

    provider = runtime_provider_for_topology(dep.runtime_target)
    rows = list_runtime_resources(db, deployment_id)
    node_rows = [r for r in rows if r.resource_type == "node" and r.node_id is not None]
    if not node_rows:
        nodes = list(
            db.scalars(
                select(TopologyNode).where(TopologyNode.topology_id == dep.topology_id)
            ).all()
        )
        targets: list[tuple[UUID, str]] = [(n.id, n.name) for n in nodes]
    else:
        targets = [(r.node_id, r.name) for r in node_rows if r.node_id is not None]

    items: list[dict] = []
    agg: list[str] = []
    for nid, name in targets:
        text = provider.fetch_logs_for_node(
            dep.topology_id,
            nid,
            tail,
            deployment_id=dep.id,
            project_id=topo.project_id,
        )
        item = {
            "node_id": str(nid),
            "service_id": str(nid),
            "name": name,
            "logs": text or "",
        }
        if text is None:
            item["error"] = "logs not available (runtime executor or provider)"
        items.append(item)
        agg.append(f"--- node {nid} ({name}) ---\n{item.get('logs') or item.get('error', '')}")

    return RuntimeOperationsLogsResponse(
        deployment_id=deployment_id,
        logs="\n".join(agg),
        items=items,
        runtime_provider=prov_name,
    )


def fetch_runtime_service_logs(
    db: Session, deployment_id: UUID, runtime_resource_id: UUID, tail: int = 100
) -> RuntimeOperationsLogsResponse:
    row = get_runtime_resource_row(db, deployment_id, runtime_resource_id)
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    wid = workload_node_id(row)
    if wid is None:
        raise ValueError("runtime resource has no workload node id")
    tail = max(1, min(int(tail or 100), 5000))
    prov_name = (dep.runtime_target or "docker").strip() or "docker"

    if grc.should_delegate_runtime_ops_to_go_runner():
        grc.log_runtime_op_delegation("service-logs", deployment_id, service_id=runtime_resource_id)
        data = _runner_client().get_runtime_service_logs(
            deployment_id,
            dep.topology_id,
            str(wid),
            tail=tail,
            project_id=topo.project_id,
        )
        return RuntimeOperationsLogsResponse(
            deployment_id=deployment_id,
            service_id=str(data.get("service_id") or wid),
            logs=str(data.get("logs") or ""),
            items=list(data.get("items") or []) if isinstance(data.get("items"), list) else [],
            runtime_provider=str(data.get("runtime_provider") or prov_name),
        )

    provider = runtime_provider_for_topology(dep.runtime_target)
    text = provider.fetch_logs_for_node(
        dep.topology_id,
        wid,
        tail,
        deployment_id=dep.id,
        project_id=topo.project_id,
    )
    items: list[dict] = [
        {
            "node_id": str(wid),
            "service_id": str(wid),
            "name": row.name,
            "logs": text or "",
        }
    ]
    if text is None:
        items[0]["error"] = "logs not available (runtime executor or provider)"
    return RuntimeOperationsLogsResponse(
        deployment_id=deployment_id,
        service_id=str(wid),
        logs=text or (items[0].get("error") or ""),
        items=items,
        runtime_provider=prov_name,
    )


def run_runtime_health_check(
    db: Session, deployment_id: UUID, runtime_resource_id: UUID
) -> RuntimeOperationsHealthResponse:
    row = get_runtime_resource_row(db, deployment_id, runtime_resource_id)
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    wid = workload_node_id(row)
    if wid is None:
        return RuntimeOperationsHealthResponse(
            status="unsupported",
            target="",
            message="No workload node mapped to this runtime resource.",
        )

    prov_name = (dep.runtime_target or "docker").strip().lower() or "docker"

    if grc.should_delegate_runtime_ops_to_go_runner():
        grc.log_runtime_op_delegation("health-check", deployment_id, service_id=runtime_resource_id)
        node = db.get(TopologyNode, wid)
        probe_body: dict[str, Any] | None = None
        if node is not None:
            runtime_cfg = extract_node_runtime_config(node.config)
            probe_body = health_probe_payload_for_node(image=node.image, runtime=runtime_cfg)
        data = _runner_client().post_runtime_service_health(
            deployment_id,
            dep.topology_id,
            str(wid),
            project_id=topo.project_id,
            body=probe_body,
        )
        lat = data.get("latency_ms")
        return RuntimeOperationsHealthResponse(
            status=str(data.get("status") or "failed"),
            target=str(data.get("target") or ""),
            latency_ms=int(lat) if lat is not None else None,
            message=str(data.get("message") or ""),
        )

    _log.info(
        "effective_runtime_executor=%s using control-plane health-check fallback deployment_id=%s",
        grc.effective_runtime_executor(),
        deployment_id,
    )
    url = (row.internal_url or "").strip()
    if not url:
        return RuntimeOperationsHealthResponse(
            status="unsupported",
            target="",
            message=(
                "No internal URL recorded for this resource. "
                "Set RUNTIME_EXECUTOR=go so health checks run inside the runtime via the Go runner."
            ),
        )
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(url)
        ok = r.status_code < 500
        return RuntimeOperationsHealthResponse(
            status="passed" if ok else "failed",
            target=url,
            message=f"HTTP {r.status_code} from control plane ({len(r.text)} bytes)",
        )
    except httpx.HTTPError as exc:
        if prov_name == "kubernetes":
            hint = (
                "Control plane cannot reach cluster-internal DNS from outside the cluster. "
                "Set RUNTIME_EXECUTOR=go for in-pod checks."
            )
        else:
            hint = (
                "Control plane cannot reach Docker bridge DNS from the API host. "
                "Set RUNTIME_EXECUTOR=go for in-container checks."
            )
        return RuntimeOperationsHealthResponse(
            status="unsupported",
            target=url,
            message=f"{hint} ({exc})",
        )


def _resolve_traffic_target(
    db: Session, deployment_id: UUID, topology_id: UUID, target: str
) -> str:
    t = (target or "").strip()
    if t.startswith("http://") or t.startswith("https://"):
        return t
    try:
        tid = UUID(t)
    except ValueError:
        return t
    res = db.get(DeploymentRuntimeResource, tid)
    if res is not None and res.deployment_id == deployment_id:
        w = workload_node_id(res)
        return str(w) if w is not None else t
    node = db.get(TopologyNode, tid)
    if node is not None and node.topology_id == topology_id:
        return str(tid)
    return t


def run_runtime_traffic_test(
    db: Session, deployment_id: UUID, payload: RuntimeOperationsTrafficRequest
) -> RuntimeOperationsTrafficResponse:
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")

    src_row = get_runtime_resource_row(db, deployment_id, payload.source_runtime_resource_id)
    src_wid = workload_node_id(src_row)
    if src_wid is None:
        return RuntimeOperationsTrafficResponse(
            status="failed",
            source=str(payload.source_runtime_resource_id),
            target=payload.target,
            protocol=payload.protocol,
            output="source runtime resource has no workload node id",
        )

    resolved_target = _resolve_traffic_target(db, deployment_id, dep.topology_id, payload.target)

    if grc.should_delegate_runtime_ops_to_go_runner():
        grc.log_runtime_op_delegation(
            "traffic-test",
            deployment_id,
            service_id=payload.source_runtime_resource_id,
        )
        body = {
            "topology_id": str(dep.topology_id),
            "deployment_id": str(deployment_id),
            "source_node_id": str(src_wid),
            "target": resolved_target,
            "protocol": payload.protocol,
        }
        if payload.port is not None:
            body["port"] = payload.port
        if payload.path:
            body["path"] = payload.path
        if payload.command:
            body["command"] = payload.command
        if topo.project_id is not None:
            body["project_id"] = str(topo.project_id)
        data = _runner_client().post_runtime_traffic_test(deployment_id, body)
        lat = data.get("latency_ms")
        return RuntimeOperationsTrafficResponse(
            status=str(data.get("status") or "failed"),
            source=str(src_wid),
            target=str(data.get("target") or resolved_target),
            protocol=str(data.get("protocol") or payload.protocol),
            output=str(data.get("output") or ""),
            latency_ms=int(lat) if lat is not None else None,
        )

    return RuntimeOperationsTrafficResponse(
        status="unsupported",
        source=str(src_wid),
        target=resolved_target,
        protocol=payload.protocol,
        output=(
            "Traffic tests require RUNTIME_EXECUTOR=go so probes run inside the deployment network "
            "via the Go runner."
        ),
    )
