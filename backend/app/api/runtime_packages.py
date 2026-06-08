"""Runtime package download and import routes (Steps 65–66)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.runtime_package import RuntimePackageImportResponse
from app.services.access_control import get_topology_for_user
from app.services import runtime_package_export_service as package_svc
from app.services import runtime_package_import_service as import_svc

router = APIRouter(prefix="/runtime-packages", tags=["runtime-packages"])


@router.post(
    "/import",
    response_model=RuntimePackageImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import a runtime deployment package ZIP and recreate topology metadata",
)
async def import_runtime_package(
    file: UploadFile = File(..., description="Runtime package ZIP exported from CNS"),
    project_id: UUID | None = Form(default=None),
    name: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimePackageImportResponse:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip runtime package file.")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        raw = import_svc.import_runtime_package(
            db,
            user=user,
            zip_bytes=payload,
            project_id=project_id,
            name=name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return RuntimePackageImportResponse(**raw)


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
