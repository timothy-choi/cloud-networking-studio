"""Runtime package download routes (Step 65)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.access_control import get_topology_for_user
from app.services import runtime_package_export_service as package_svc

router = APIRouter(prefix="/runtime-packages", tags=["runtime-packages"])


@router.get(
    "/{package_id}/download",
    summary="Download a generated runtime deployment package zip",
)
def download_runtime_package(
    package_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    record = package_svc.get_package_record(package_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime package not found")
    if record.topology_id.int != 0:
        get_topology_for_user(db, user, record.topology_id)
    try:
        payload = package_svc.read_package_zip(package_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    filename = f"cns-runtime-package-{package_id[:8]}.zip"
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
