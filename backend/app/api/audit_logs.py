"""Router audit log — riwayat aktivitas platform.

Otorisasi:
- **admin** melihat seluruh audit log.
- peran lain hanya melihat audit log miliknya sendiri (dibatasi di server).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.roles import Permission, has_permission
from app.database.session import get_db
from app.models.user import User
from app.schemas.audit_log import (
    AuditLogFilterMeta,
    AuditLogListResponse,
    AuditLogResponse,
)
from app.schemas.response import ApiResponse
from app.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get(
    "",
    response_model=ApiResponse[AuditLogListResponse],
    summary="Riwayat audit log",
    description=(
        "Menampilkan riwayat aksi sensitif (deploy, rollback, restart container, "
        "perubahan env var, kelola user/server, dsb).\n\n"
        "- **Admin** melihat seluruh aktivitas dan dapat memfilter per user.\n"
        "- **Developer/Viewer** hanya melihat aktivitas miliknya sendiri."
    ),
)
def list_audit_logs(
    username: str | None = Query(
        default=None, description="Filter username (khusus admin)"
    ),
    action: str | None = Query(
        default=None, description="Filter jenis aksi, mis. DEPLOY"
    ),
    date_from: datetime | None = Query(
        default=None, alias="from", description="Batas awal waktu (ISO 8601)"
    ),
    date_to: datetime | None = Query(
        default=None, alias="to", description="Batas akhir waktu (ISO 8601)"
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Jumlah baris per halaman"),
    offset: int = Query(default=0, ge=0, description="Jumlah baris yang dilewati"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AuditLogListResponse]:
    is_admin = has_permission(current_user.role, Permission.AUDIT_READ_ALL)

    if not is_admin:
        if username is not None and username != current_user.username:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Hanya admin yang dapat melihat audit log user lain",
            )
        username = current_user.username

    items, total = audit_service.list_entries(
        db,
        username=username,
        action=action,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(
        data=AuditLogListResponse(
            items=[AuditLogResponse.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/filters",
    response_model=ApiResponse[AuditLogFilterMeta],
    summary="Metadata filter audit log",
    description=(
        "Daftar action dan username yang tersedia untuk dropdown filter. "
        "Untuk non-admin, daftar username dibatasi ke akun sendiri."
    ),
)
def get_audit_filters(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AuditLogFilterMeta]:
    is_admin = has_permission(current_user.role, Permission.AUDIT_READ_ALL)
    actions, usernames = audit_service.get_filter_meta(db)

    if not is_admin:
        usernames = [current_user.username]

    return ApiResponse(
        data=AuditLogFilterMeta(
            actions=actions,
            usernames=usernames,
            is_admin=is_admin,
        )
    )
