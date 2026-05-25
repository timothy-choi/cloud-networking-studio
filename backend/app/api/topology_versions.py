"""Topology version API routes (Step 56)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.secret_masking import scrub_sensitive_dict
from app.db.session import get_db
from app.models.user import User
from app.schemas.topology_version import (
    TopologyVersionCreate,
    TopologyVersionDetailResponse,
    TopologyVersionDiffResponse,
    TopologyVersionListResponse,
    TopologyVersionResponse,
    TopologyVersionRollbackImpact,
    TopologyVersionRollbackRequest,
    TopologyVersionRollbackResponse,
)
from app.services.access_control import (
    get_topology_for_user,
    require_project_owner,
    require_topology_editor,
)
from app.services.audit_service import record_audit
from app.services.topology_version_diff_service import diff_topology_snapshots
from app.services import topology_version_service as version_svc
from app.services import topology_rollback_service as rollback_svc

router = APIRouter(prefix="/topologies/{topology_id}/versions", tags=["topology-versions"])


def _to_response(v) -> TopologyVersionResponse:
    return TopologyVersionResponse.model_validate(v)


def _impact_from_dict(raw: dict) -> TopologyVersionRollbackImpact:
    return TopologyVersionRollbackImpact.model_validate(raw)


@router.get("", response_model=TopologyVersionListResponse)
def list_topology_versions(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyVersionListResponse:
    get_topology_for_user(db, user, topology_id)
    items = [_to_response(v) for v in version_svc.list_versions(db, topology_id)]
    return TopologyVersionListResponse(items=items)


@router.post("", response_model=TopologyVersionResponse, status_code=status.HTTP_201_CREATED)
def create_topology_version(
    topology_id: UUID,
    body: TopologyVersionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyVersionResponse:
    require_topology_editor(db, user, topology_id)
    topo = version_svc.load_topology_with_graph(db, topology_id)
    if topo is None:
        raise HTTPException(status_code=404, detail="Not found")
    version = version_svc.create_topology_version(
        db,
        topology=topo,
        created_by=user,
        source="manual",
        name=body.name,
        description=body.description,
    )
    record_audit(
        db,
        action="topology.version.created",
        resource_type="topology_version",
        resource_id=version.id,
        project_id=topo.project_id,
        actor_user_id=user.id,
        status="success",
        metadata=scrub_sensitive_dict(
            {
                "topology_id": str(topology_id),
                "version_number": version.version_number,
                "source": "manual",
            }
        ),
    )
    db.commit()
    db.refresh(version)
    return _to_response(version)


@router.get("/{version_id}", response_model=TopologyVersionDetailResponse)
def get_topology_version(
    topology_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyVersionDetailResponse:
    get_topology_for_user(db, user, topology_id)
    version = version_svc.get_version_for_topology(db, topology_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Not found")
    data = TopologyVersionDetailResponse.model_validate(version)
    data.snapshot_json = scrub_sensitive_dict(version.snapshot_json) or {}
    return data


@router.get("/{version_id}/rollback-impact", response_model=TopologyVersionRollbackImpact)
def get_rollback_impact(
    topology_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyVersionRollbackImpact:
    topo = version_svc.load_topology_with_graph(db, topology_id)
    if topo is None:
        raise HTTPException(status_code=404, detail="Not found")
    get_topology_for_user(db, user, topology_id)
    version = version_svc.get_version_for_topology(db, topology_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _impact_from_dict(
        rollback_svc.compute_rollback_impact(db, topology=topo, version=version)
    )


@router.get("/{version_id}/diff", response_model=TopologyVersionDiffResponse)
def diff_topology_versions(
    topology_id: UUID,
    version_id: UUID,
    against: UUID = Query(..., description="Other version id to compare against."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyVersionDiffResponse:
    get_topology_for_user(db, user, topology_id)
    left = version_svc.get_version_for_topology(db, topology_id, against)
    right = version_svc.get_version_for_topology(db, topology_id, version_id)
    if left is None or right is None:
        raise HTTPException(status_code=404, detail="Not found")
    diff = diff_topology_snapshots(left.snapshot_json, right.snapshot_json)
    return TopologyVersionDiffResponse(
        base_version_id=against,
        compare_version_id=version_id,
        diff=diff,
    )


@router.post("/{version_id}/rollback", response_model=TopologyVersionRollbackResponse)
def rollback_topology_version(
    topology_id: UUID,
    version_id: UUID,
    body: TopologyVersionRollbackRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyVersionRollbackResponse:
    topo = version_svc.load_topology_with_graph(db, topology_id)
    if topo is None:
        raise HTTPException(status_code=404, detail="Not found")
    require_project_owner(db, user, topo.project_id)
    version = version_svc.get_version_for_topology(db, topology_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Not found")

    mode = body.mode if body else "config_only"
    result = rollback_svc.execute_rollback(
        db,
        topology=topo,
        version=version,
        actor=user,
        mode=mode,  # type: ignore[arg-type]
    )

    try:
        from app.services.notification_service import notify_project_members

        notify_project_members(
            db,
            project_id=topo.project_id,
            type="topology.rollback",
            title=f"Topology rolled back: {topo.name}",
            message=(
                f"{user.email or user.id} rolled back topology '{topo.name}' "
                f"to version {version.version_number} (mode={mode})."
            ),
            severity="warning",
            metadata=scrub_sensitive_dict(
                {
                    "topology_id": str(topology_id),
                    "version_id": str(version_id),
                    "mode": mode,
                }
            ),
        )
    except Exception:
        pass
    db.commit()
    db.refresh(result["version"])
    return TopologyVersionRollbackResponse(
        version=_to_response(result["version"]),
        mode=result["mode"],
        message=result["message"],
        impact=_impact_from_dict(result["impact"]),
        destroyed_deployment_ids=[UUID(x) for x in result["destroyed_deployment_ids"]],
        redeployed_deployment_id=(
            UUID(result["redeployed_deployment_id"])
            if result["redeployed_deployment_id"]
            else None
        ),
    )
