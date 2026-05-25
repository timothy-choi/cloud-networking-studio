"""Rollback impact analysis and modes (Step 56+)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.secret_masking import scrub_sensitive_dict
from app.models.deployment import (
    Deployment,
    DeploymentEvent,
    DeploymentEventLevel,
    TopologySyncStatus,
)
from app.models.topology import Topology
from app.models.topology_version import TopologyVersion
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.deployment_destroy_service import destroy_deployment_record
from app.services.deployment_queries import list_active_deployments_for_topology
from app.services import topology_version_service as version_svc
from app.services import topology_deploy_execution as deploy_exec

RollbackMode = Literal["config_only", "rollback_and_destroy", "rollback_and_redeploy"]


def _node_names(snapshot: dict[str, Any]) -> set[str]:
    return {str(n.get("name") or "") for n in snapshot.get("nodes") or [] if n.get("name")}


def _nodes_with_services(snapshot: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for n in snapshot.get("nodes") or []:
        cfg = n.get("config") or {}
        ports = cfg.get("ports") or cfg.get("services")
        if ports and n.get("name"):
            names.add(str(n["name"]))
    return names


def _deployed_node_names(dep: Deployment) -> set[str]:
    eff = dep.effective_config_json or {}
    return {str(n.get("name") or "") for n in eff.get("nodes") or [] if n.get("name")}


def compute_rollback_impact(
    db: Session,
    *,
    topology: Topology,
    version: TopologyVersion,
) -> dict[str, Any]:
    """Analyze how rolling back to ``version`` affects the live topology and active deployments."""
    current = version_svc.build_topology_snapshot(topology)
    target = version.snapshot_json or {}
    current_names = _node_names(current)
    target_names = _node_names(target)
    removed = sorted(current_names - target_names)
    added = sorted(target_names - current_names)
    removed_services = sorted(_nodes_with_services(current) - target_names)

    active = list_active_deployments_for_topology(db, topology.id)
    deployed_names: set[str] = set()
    for dep in active:
        deployed_names |= _deployed_node_names(dep)
        if not deployed_names:
            deployed_names |= current_names

    nodes_removed_from_runtime = sorted(deployed_names - target_names)
    removes_deployed_nodes = bool(nodes_removed_from_runtime) or (
        bool(deployed_names) and not target_names
    )

    warning_parts: list[str] = []
    if active:
        warning_parts.append(
            f"{len(active)} active deployment(s) may no longer match the rolled-back topology."
        )
    if removes_deployed_nodes:
        if not target_names:
            warning_parts.append(
                "Rollback target has no nodes; runtime workloads would outlive an empty topology definition."
            )
        else:
            warning_parts.append(
                f"Nodes currently deployed but absent after rollback: {', '.join(nodes_removed_from_runtime)}."
            )
    if removed_services:
        warning_parts.append(
            f"Exposed services on removed nodes: {', '.join(removed_services)}."
        )
    warning_message = " ".join(warning_parts) if warning_parts else None

    return {
        "active_deployment_count": len(active),
        "active_deployments": [
            {
                "id": str(dep.id),
                "status": dep.status.value,
                "topology_sync_status": dep.topology_sync_status.value
                if hasattr(dep.topology_sync_status, "value")
                else dep.topology_sync_status,
            }
            for dep in active
        ],
        "nodes_removed": removed,
        "nodes_added": added,
        "services_removed": removed_services,
        "removes_deployed_nodes": removes_deployed_nodes,
        "nodes_removed_from_runtime": nodes_removed_from_runtime,
        "target_node_count": len(target_names),
        "current_node_count": len(current_names),
        "warning_message": warning_message,
    }


def _mark_deployments_out_of_sync(
    db: Session,
    deployments: list[Deployment],
    *,
    rollback_version_number: int,
) -> None:
    msg = (
        f"Topology rolled back to v{rollback_version_number}; "
        "deployment is out of sync with current topology config."
    )
    for dep in deployments:
        dep.topology_sync_status = TopologySyncStatus.OUT_OF_SYNC
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.WARNING,
                message=msg,
            )
        )


def execute_rollback(
    db: Session,
    *,
    topology: Topology,
    version: TopologyVersion,
    actor: User,
    mode: RollbackMode = "config_only",
) -> dict[str, Any]:
    """Rollback topology config and apply deployment impact handling for ``mode``."""
    impact = compute_rollback_impact(db, topology=topology, version=version)
    active_before = list_active_deployments_for_topology(db, topology.id)

    destroyed_ids: list[str] = []
    redeployed_id: str | None = None
    message = "Topology restored from snapshot."

    if mode in ("rollback_and_destroy", "rollback_and_redeploy"):
        for dep in active_before:
            destroy_deployment_record(
                db,
                dep=dep,
                topo=topology,
                actor=actor,
                audit_action="topology.version.rollback_destroy",
                audit_metadata=scrub_sensitive_dict(
                    {
                        "topology_id": str(topology.id),
                        "rollback_version_id": str(version.id),
                        "mode": mode,
                    }
                ),
            )
            destroyed_ids.append(str(dep.id))
        message = f"Prior {len(destroyed_ids)} deployment(s) destroyed; rolling back topology config."

    rollback_version = version_svc.rollback_topology_to_version(
        db,
        topology=topology,
        version=version,
        actor=actor,
    )

    if mode == "config_only":
        if active_before:
            _mark_deployments_out_of_sync(
                db,
                active_before,
                rollback_version_number=version.version_number,
            )
            message = (
                "Topology config rolled back. Active deployments marked out of sync — "
                "destroy or redeploy to align runtime."
            )
    elif mode == "rollback_and_destroy":
        message = (
            f"Topology rolled back and {len(destroyed_ids)} deployment(s) destroyed."
            if destroyed_ids
            else "Topology rolled back; no active deployments required destroy."
        )
    elif mode == "rollback_and_redeploy":
        target_nodes = _node_names(version.snapshot_json or {})
        if target_nodes:
            out = deploy_exec.execute_topology_deploy(db, actor, topology.id)
            if isinstance(out, Deployment):
                redeployed_id = str(out.id)
                message = (
                    "Topology rolled back, prior deployments destroyed, and redeploy started."
                )
            else:
                message = (
                    "Topology rolled back and prior deployments destroyed, "
                    "but redeploy failed validation."
                )
        else:
            message = (
                "Topology rolled back to an empty graph; prior deployments destroyed. "
                "Redeploy skipped — add nodes before deploying."
            )
    else:
        raise ValueError(f"Unknown rollback mode: {mode}")

    record_audit(
        db,
        action="topology.version.rollback",
        resource_type="topology_version",
        resource_id=rollback_version.id,
        project_id=topology.project_id,
        actor_user_id=actor.id,
        status="success",
        metadata=scrub_sensitive_dict(
            {
                "topology_id": str(topology.id),
                "mode": mode,
                "from_version_id": str(version.id),
                "destroyed_deployment_ids": destroyed_ids,
                "redeployed_deployment_id": redeployed_id,
                "impact": impact,
            }
        ),
    )

    return {
        "version": rollback_version,
        "mode": mode,
        "message": message,
        "impact": impact,
        "destroyed_deployment_ids": destroyed_ids,
        "redeployed_deployment_id": redeployed_id,
    }
