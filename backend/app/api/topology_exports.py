"""Step 52A: topology IaC export download routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.access_control import get_topology_for_user
from app.services import topology_iac_export_service as iac_svc

router = APIRouter(prefix="/topologies", tags=["topologies"])


def _bundle(db: Session, user: User, topology_id: UUID):
    get_topology_for_user(db, user, topology_id)
    try:
        return iac_svc.load_topology_export_bundle(db, topology_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topology not found") from None


@router.get(
    "/{topology_id}/exports/docker-compose",
    summary="Download Docker Compose blueprint generated from topology",
)
def export_topology_docker_compose(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    bundle = _bundle(db, user, topology_id)
    content = iac_svc.generate_docker_compose(bundle)
    return Response(
        content=content.encode("utf-8"),
        media_type="application/yaml; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{iac_svc.DOCKER_COMPOSE_FILENAME}"'},
    )


@router.get(
    "/{topology_id}/exports/kubernetes",
    summary="Download Kubernetes YAML blueprint generated from topology",
)
def export_topology_kubernetes(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    bundle = _bundle(db, user, topology_id)
    content = iac_svc.generate_kubernetes_yaml(bundle)
    return Response(
        content=content.encode("utf-8"),
        media_type="application/yaml; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{iac_svc.KUBERNETES_FILENAME}"'},
    )


@router.get(
    "/{topology_id}/exports/terraform",
    summary="Download Terraform skeleton zip generated from topology",
)
def export_topology_terraform(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    bundle = _bundle(db, user, topology_id)
    payload = iac_svc.build_terraform_zip(bundle)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{iac_svc.TERRAFORM_ZIP_NAME}"'},
    )


@router.get(
    "/{topology_id}/exports/ansible",
    summary="Download Ansible skeleton zip generated from topology",
)
def export_topology_ansible(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    bundle = _bundle(db, user, topology_id)
    payload = iac_svc.build_ansible_zip(bundle)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{iac_svc.ANSIBLE_ZIP_NAME}"'},
    )


@router.get(
    "/{topology_id}/exports/archive",
    summary="Download all IaC export artifacts as a zip archive",
)
def export_topology_iac_archive(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    bundle = _bundle(db, user, topology_id)
    payload = iac_svc.build_iac_archive(bundle)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{iac_svc.ARCHIVE_ZIP_NAME}"'},
    )
