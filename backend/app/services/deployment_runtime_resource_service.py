"""Persist ``runtime_access`` payloads from the Go runner onto ``DeploymentRuntimeResource`` rows."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.deployment_runtime_resource import DeploymentRuntimeResource


def _parse_uuid(val: str | None) -> uuid.UUID | None:
    if not val or not str(val).strip():
        return None
    try:
        return uuid.UUID(str(val).strip())
    except ValueError:
        return None


def replace_runtime_resources_from_payload(
    db: Session, deployment_id: uuid.UUID, runtime_access: dict[str, Any]
) -> None:
    """Replace all persisted access rows for a deployment (idempotent on re-deploy)."""
    db.execute(
        delete(DeploymentRuntimeResource).where(
            DeploymentRuntimeResource.deployment_id == deployment_id
        )
    )
    prov = str(runtime_access.get("runtime_provider") or "").strip() or "unknown"
    ns = runtime_access.get("namespace_or_network")
    ns_s = str(ns).strip() if ns is not None else None
    for row in runtime_access.get("resources") or []:
        if not isinstance(row, dict):
            continue
        rtype = str(row.get("type") or "unknown").strip()[:32]
        name = str(row.get("name") or rtype)[:512]
        runtime_name = str(row.get("runtime_name") or name)[:512]
        status = row.get("status")
        status_s = str(status)[:64] if status is not None else None
        nn = row.get("namespace_or_network")
        nn_s = str(nn).strip() if nn is not None else (ns_s or None)
        ports = row.get("ports")
        if ports is not None and not isinstance(ports, (list, dict)):
            ports = None
        meta = row.get("metadata")
        if meta is not None and not isinstance(meta, dict):
            meta = None
        ext = row.get("external_url")
        ext_s = str(ext) if ext is not None else None
        db.add(
            DeploymentRuntimeResource(
                deployment_id=deployment_id,
                resource_type=rtype,
                node_id=_parse_uuid(row.get("node_id")),
                service_id=_parse_uuid(row.get("service_id")),
                name=name,
                runtime_name=runtime_name,
                runtime_provider=prov[:32],
                namespace_or_network=(nn_s[:512] if nn_s else None),
                status=status_s,
                ports_json=ports,
                internal_url=(str(row["internal_url"]) if row.get("internal_url") else None),
                external_url=ext_s,
                access_metadata=meta,
            )
        )


def list_runtime_resources(db: Session, deployment_id: uuid.UUID) -> list[DeploymentRuntimeResource]:
    return list(
        db.scalars(
            select(DeploymentRuntimeResource)
            .where(DeploymentRuntimeResource.deployment_id == deployment_id)
            .order_by(DeploymentRuntimeResource.created_at)
        ).all()
    )


def resource_row_to_public_dict(r: DeploymentRuntimeResource) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "type": r.resource_type,
        "node_id": str(r.node_id) if r.node_id else None,
        "service_id": str(r.service_id) if r.service_id else None,
        "name": r.name,
        "runtime_name": r.runtime_name,
        "runtime_provider": r.runtime_provider,
        "namespace_or_network": r.namespace_or_network,
        "status": r.status,
        "ports": r.ports_json,
        "internal_url": r.internal_url,
        "external_url": r.external_url,
        "metadata": r.access_metadata,
    }
