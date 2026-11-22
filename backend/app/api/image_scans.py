"""API pemindaian kerentanan image container."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.permissions import require_permission
from app.core.roles import Permission, Role
from app.database.session import get_db
from app.models.image_scan import ImageScan
from app.models.user import User
from app.repositories import image_scan_repository
from app.schemas.image_scan import (
    ImageScanDetail,
    ImageScanListResponse,
    ImageScanSummary,
    ImageScanTrigger,
)
from app.schemas.response import ApiResponse
from app.services import image_scan_service, project_service

router = APIRouter(prefix="/image-scans", tags=["image-scans"])


def _is_admin(user: User) -> bool:
    return user.role == Role.ADMIN.value


def _require_project_access(db: Session, project_id: int | None, user: User) -> None:
    if project_id is None:
        return
    project = project_service.get_project_by_id(db, project_id)
    if project is None or (project.owner_id != user.id and not _is_admin(user)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project tidak ditemukan")


def _detail(scan: ImageScan) -> ImageScanDetail:
    return ImageScanDetail.model_validate(scan)


def _get_accessible(db: Session, scan_id: int, user: User) -> ImageScan:
    scan = image_scan_repository.get_accessible_by_id(
        db,
        scan_id,
        user_id=user.id,
        username=user.username,
        is_admin=_is_admin(user),
    )
    if scan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan tidak ditemukan")
    return scan


@router.post(
    "",
    response_model=ApiResponse[ImageScanDetail],
    status_code=status.HTTP_201_CREATED,
    summary="Pindai kerentanan image container",
    description=(
        "Menjalankan Trivy terhadap referensi image dan menyimpan ringkasan "
        "temuan CVE. Jika scanner tidak tersedia atau timeout, baris scan tetap "
        "dibuat dengan status `failed` agar kegagalan dapat ditelusuri."
    ),
    responses={
        403: {"description": "Tidak punya izin image:scan"},
        404: {"description": "Project tidak ditemukan"},
    },
)
async def trigger_image_scan(
    payload: ImageScanTrigger,
    current_user: User = Depends(require_permission(Permission.IMAGE_SCAN)),
    db: Session = Depends(get_db),
) -> ApiResponse[ImageScanDetail]:
    _require_project_access(db, payload.project_id, current_user)
    scan = image_scan_service.create_scan(
        db,
        image_name=payload.image_name,
        project_id=payload.project_id,
        requested_by=current_user.username,
    )
    scan = await image_scan_service.execute_scan(db, scan)
    return ApiResponse(data=_detail(scan))


@router.get(
    "",
    response_model=ApiResponse[ImageScanListResponse],
    summary="Riwayat pemindaian image",
    description=(
        "Menampilkan riwayat scan yang dapat diakses user: miliknya sendiri "
        "atau project yang ia miliki. Admin melihat semua scan."
    ),
)
def list_image_scans(
    project_id: int | None = Query(default=None, ge=1),
    image: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ImageScanListResponse]:
    scans, total = image_scan_repository.list_scans(
        db,
        user_id=current_user.id,
        username=current_user.username,
        is_admin=_is_admin(current_user),
        project_id=project_id,
        image=image,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(
        data=ImageScanListResponse(
            items=[ImageScanSummary.model_validate(scan) for scan in scans],
            total=total,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/{scan_id}",
    response_model=ApiResponse[ImageScanDetail],
    summary="Detail pemindaian image",
    description="Menampilkan ringkasan severity dan daftar temuan CVE sebuah scan.",
)
def get_image_scan(
    scan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ImageScanDetail]:
    scan = _get_accessible(db, scan_id, current_user)
    return ApiResponse(data=_detail(scan))


@router.post(
    "/{scan_id}/rescan",
    response_model=ApiResponse[ImageScanDetail],
    status_code=status.HTTP_201_CREATED,
    summary="Pindai ulang image",
    description=(
        "Membuat baris scan baru dengan image dan project yang sama, lalu "
        "menjalankan Trivy kembali. Riwayat scan sebelumnya tidak diubah."
    ),
    responses={403: {"description": "Tidak punya izin image:scan"}},
)
async def rescan_image(
    scan_id: int,
    current_user: User = Depends(require_permission(Permission.IMAGE_SCAN)),
    db: Session = Depends(get_db),
) -> ApiResponse[ImageScanDetail]:
    original = _get_accessible(db, scan_id, current_user)
    scan = image_scan_service.create_rescan(
        db, original, requested_by=current_user.username
    )
    scan = await image_scan_service.execute_scan(db, scan)
    return ApiResponse(data=_detail(scan))
