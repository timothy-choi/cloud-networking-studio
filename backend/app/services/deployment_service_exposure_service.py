"""Create/list/expire deployment service exposures (Step 40)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.deployment import Deployment
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.deployment_service_exposure import DeploymentServiceExposure


class DuplicateExposureError(Exception):
    """An active exposure already exists for this runtime service row."""


def _meta_dict(meta: dict[str, Any] | None) -> dict[str, Any]:
    return dict(meta) if meta else {}


def resolve_service_resource(
    db: Session, deployment_id: UUID, service_id: UUID
) -> DeploymentRuntimeResource | None:
    """Match ``service_id`` path segment to a persisted *service* row (by row id or topology service_id)."""
    row = db.get(DeploymentRuntimeResource, service_id)
    if (
        row
        and row.deployment_id == deployment_id
        and row.resource_type == "service"
    ):
        return row
    return db.scalar(
        select(DeploymentRuntimeResource).where(
            DeploymentRuntimeResource.deployment_id == deployment_id,
            DeploymentRuntimeResource.resource_type == "service",
            DeploymentRuntimeResource.service_id == service_id,
        )
    )


def mark_expired_exposures(db: Session, deployment_id: UUID) -> None:
    now = datetime.now(UTC)
    db.execute(
        update(DeploymentServiceExposure)
        .where(
            DeploymentServiceExposure.deployment_id == deployment_id,
            DeploymentServiceExposure.status == "active",
            DeploymentServiceExposure.expires_at.is_not(None),
            DeploymentServiceExposure.expires_at < now,
        )
        .values(status="expired", updated_at=now)
    )


def list_exposure_rows(db: Session, deployment_id: UUID) -> list[DeploymentServiceExposure]:
    mark_expired_exposures(db, deployment_id)
    return list(
        db.scalars(
            select(DeploymentServiceExposure)
            .where(DeploymentServiceExposure.deployment_id == deployment_id)
            .order_by(DeploymentServiceExposure.created_at.desc())
        ).all()
    )


def exposure_to_api_dict(e: DeploymentServiceExposure) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "deployment_id": str(e.deployment_id),
        "runtime_resource_id": str(e.runtime_resource_id),
        "exposure_type": e.exposure_type,
        "external_url": e.external_url,
        "external_host": e.external_host,
        "external_port": e.external_port,
        "status": e.status,
        "expires_at": e.expires_at.isoformat() if e.expires_at else None,
        "metadata": e.exposure_metadata,
        "created_at": e.created_at.isoformat(),
        "updated_at": e.updated_at.isoformat(),
    }


def _try_docker_published_url(container_id: str) -> tuple[str | None, str | None, int | None, dict[str, Any]]:
    """Return (exposure_type, external_url, external_port, metadata) for a running Docker container."""
    meta: dict[str, Any] = {}
    if os.environ.get("CNS_USE_FAKE_DOCKER") == "1":
        meta["note"] = "Fake Docker provider — no host port bindings to inspect."
        meta["manual_port_forward_required"] = True
        return "port_forward", None, None, meta
    try:
        import docker

        client = docker.from_env()
        insp = client.api.inspect_container(container_id)
        ports = (insp.get("NetworkSettings") or {}).get("Ports") or {}
        for cport, bindings in ports.items():
            if not bindings:
                continue
            b0 = bindings[0]
            raw_host = b0.get("HostIp")
            if raw_host in (None, "", "0.0.0.0"):
                host = "127.0.0.1"
            else:
                host = raw_host
            hp = int(b0["HostPort"])
            url = f"http://{host}:{hp}/"
            meta["container_port"] = cport
            meta["inspect_host_binding"] = f"{host}:{hp}"
            return "docker_host_port", url, hp, meta
        meta["manual_port_forward_required"] = True
        meta["note"] = (
            "No published host ports on this container. Use docker run -p, compose ports:, "
            "or kubectl/docker port-forward patterns from your environment."
        )
        return "port_forward", None, None, meta
    except Exception as exc:  # noqa: BLE001 — best-effort inspect
        meta["manual_port_forward_required"] = True
        meta["inspect_error"] = str(exc)
        return "port_forward", None, None, meta


def _build_kubernetes_exposure(dep: Deployment, res: DeploymentRuntimeResource) -> tuple[str, str | None, str | None, int | None, dict[str, Any]]:
    ns = (res.namespace_or_network or "").strip()
    svc = (res.runtime_name or "").strip()
    meta: dict[str, Any] = {
        "manual_port_forward_required": True,
        "commands": [
            f"kubectl port-forward -n {ns} svc/{svc} 18080:80",
            "curl -sS http://127.0.0.1:18080/",
        ],
        "notes": "ClusterIP services are not publicly reachable without Ingress/NodePort; port-forward is the supported baseline.",
    }
    if ns and svc:
        return "kubernetes_service", None, None, None, meta
    return "port_forward", None, None, None, meta


def _build_docker_exposure(dep: Deployment, res: DeploymentRuntimeResource) -> tuple[str, str | None, str | None, int | None, dict[str, Any]]:
    meta = _meta_dict(res.access_metadata)
    cid = None
    if isinstance(meta.get("container_id"), str):
        cid = meta["container_id"]
    if cid:
        et, url, port, extra = _try_docker_published_url(cid)
        meta = {**meta, **extra}
        host = None
        if url and port is not None:
            host = "127.0.0.1"
        return et, url, host, port, meta
    meta["manual_port_forward_required"] = True
    meta["commands"] = [
        f"# Reach by container DNS on the lab bridge, or: docker exec -it {res.runtime_name} sh",
        f"# If ports are published: curl http://127.0.0.1:<host-port>/",
    ]
    return "port_forward", None, None, None, meta


def compute_exposure_payload(dep: Deployment, res: DeploymentRuntimeResource) -> tuple[str, str | None, str | None, int | None, dict[str, Any]]:
    if dep.runtime_target == "kubernetes":
        return _build_kubernetes_exposure(dep, res)
    return _build_docker_exposure(dep, res)


def create_exposure(
    db: Session,
    dep: Deployment,
    service_id: UUID,
    *,
    ttl_hours: int | None,
) -> DeploymentServiceExposure:
    res = resolve_service_resource(db, dep.id, service_id)
    if res is None:
        raise ValueError("service resource not found")

    mark_expired_exposures(db, dep.id)
    existing = db.scalar(
        select(DeploymentServiceExposure).where(
            DeploymentServiceExposure.deployment_id == dep.id,
            DeploymentServiceExposure.runtime_resource_id == res.id,
            DeploymentServiceExposure.status == "active",
        )
    )
    if existing is not None:
        raise DuplicateExposureError()

    etype, ext_url, host, port, meta = compute_exposure_payload(dep, res)
    now = datetime.now(UTC)
    expires_at = None
    if ttl_hours is not None:
        expires_at = now + timedelta(hours=int(ttl_hours))

    row = DeploymentServiceExposure(
        deployment_id=dep.id,
        runtime_resource_id=res.id,
        exposure_type=etype,
        external_url=ext_url,
        external_host=host,
        external_port=port,
        status="active",
        expires_at=expires_at,
        exposure_metadata=meta,
    )
    db.add(row)
    db.flush()
    return row


def remove_exposure(db: Session, dep: Deployment, service_id: UUID) -> bool:
    res = resolve_service_resource(db, dep.id, service_id)
    if res is None:
        raise ValueError("service resource not found")
    exp = db.scalar(
        select(DeploymentServiceExposure).where(
            DeploymentServiceExposure.deployment_id == dep.id,
            DeploymentServiceExposure.runtime_resource_id == res.id,
            DeploymentServiceExposure.status == "active",
        )
    )
    if exp is None:
        return False
    exp.status = "removed"
    exp.updated_at = datetime.now(UTC)
    return True
