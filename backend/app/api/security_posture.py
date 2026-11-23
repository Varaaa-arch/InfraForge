"""API ringkasan posture keamanan platform."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.roles import Permission
from app.database.session import get_db
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.security_posture import SecurityPostureSummary
from app.services import security_posture_service

router = APIRouter(prefix="/security", tags=["security-posture"])


@router.get(
    "/posture",
    response_model=ApiResponse[SecurityPostureSummary],
    summary="Ringkasan posture keamanan",
    description=(
        "Menggabungkan temuan CVE image, status sertifikat TLS, dan pemeriksaan "
        "konfigurasi container dari Docker attrs menjadi skor posture 0–100. "
        "Semua peran dapat membaca ringkasan ini."
    ),
)
def get_security_posture(
    _: User = Depends(require_permission(Permission.SECURITY_READ)),
    db: Session = Depends(get_db),
) -> ApiResponse[SecurityPostureSummary]:
    return ApiResponse(data=security_posture_service.build_posture(db))
