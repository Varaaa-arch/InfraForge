"""API target TLS/SSL: konfigurasi domain dan pemeriksaan sertifikat."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.core.permissions import require_permission
from app.core.roles import Permission
from app.database.session import get_db
from app.models.tls_domain import TlsDomain, TlsDomainStatus
from app.models.user import User
from app.repositories import tls_domain_repository
from app.schemas.response import ApiResponse
from app.schemas.tls_domain import (
    TlsDomainCheckResponse,
    TlsDomainCreate,
    TlsDomainDetailResponse,
    TlsDomainListResponse,
    TlsDomainResponse,
    TlsDomainUpdate,
)
from app.services import tls_domain_service

router = APIRouter(prefix="/tls-domains", tags=["tls-domains"])


def _get_domain(db: Session, domain_id: int) -> TlsDomain:
    domain = tls_domain_repository.get_by_id(db, domain_id)
    if domain is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Domain TLS tidak ditemukan")
    return domain


def _detail(db: Session, domain: TlsDomain) -> TlsDomainDetailResponse:
    checks = tls_domain_repository.list_checks(db, domain.id, limit=20)
    data = TlsDomainResponse.model_validate(domain).model_dump()
    return TlsDomainDetailResponse(
        **data,
        checks=[TlsDomainCheckResponse.model_validate(check) for check in checks],
    )


def _validate(host: str, port: int) -> str:
    try:
        return tls_domain_service.validate_target(host, port)
    except tls_domain_service.TlsTargetError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


async def _inspect(
    db: Session, domain: TlsDomain, *, force: bool = False
) -> TlsDomain:
    try:
        result = await asyncio.to_thread(
            tls_domain_service.inspect_target,
            domain.host,
            domain.port,
            domain.warning_days,
            use_cache=not force,
        )
    except tls_domain_service.TlsTargetError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    domain, _ = tls_domain_service.apply_result(db, domain, result)
    return domain


@router.get(
    "",
    response_model=ApiResponse[TlsDomainListResponse],
    summary="Daftar target TLS/SSL",
    description="Menampilkan domain yang dipantau beserta status sertifikat terakhir.",
)
def list_tls_domains(
    search: str | None = Query(default=None, max_length=253),
    tls_status: TlsDomainStatus | None = Query(default=None, alias="status"),
    enabled: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TlsDomainListResponse]:
    domains, total = tls_domain_repository.list_domains(
        db,
        search=search,
        status=tls_status,
        enabled=enabled,
        skip=offset,
        limit=limit,
    )
    return ApiResponse(
        data=TlsDomainListResponse(
            items=[TlsDomainResponse.model_validate(item) for item in domains],
            total=total,
        )
    )


@router.post(
    "",
    response_model=ApiResponse[TlsDomainDetailResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Tambah target TLS/SSL",
    description=(
        "Mendaftarkan host/port untuk dipantau. Pemeriksaan pertama dijalankan "
        "kecuali `check_now=false`."
    ),
    responses={
        403: {"description": "Tidak punya izin tls_domain:write"},
        409: {"description": "Host/port sudah terdaftar"},
        422: {"description": "Host/port tidak valid atau diblokir"},
    },
)
async def create_tls_domain(
    payload: TlsDomainCreate,
    current_user: User = Depends(require_permission(Permission.TLS_DOMAIN_WRITE)),
    db: Session = Depends(get_db),
) -> ApiResponse[TlsDomainDetailResponse]:
    if tls_domain_repository.count_domains(db) >= settings.TLS_DOMAIN_MAX_TARGETS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Batas maksimum {settings.TLS_DOMAIN_MAX_TARGETS} target TLS tercapai",
        )
    host = _validate(payload.host, payload.port)
    if tls_domain_repository.get_by_host_port(db, host, payload.port) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Host dan port tersebut sudah terdaftar"
        )
    domain = tls_domain_repository.create(
        db,
        name=payload.name,
        host=host,
        port=payload.port,
        enabled=payload.enabled,
        warning_days=payload.warning_days,
        created_by=current_user.username,
    )
    if payload.check_now:
        domain = await _inspect(db, domain)
    return ApiResponse(data=_detail(db, domain))


@router.get(
    "/{domain_id}",
    response_model=ApiResponse[TlsDomainDetailResponse],
    summary="Detail target TLS/SSL",
    description="Menampilkan detail sertifikat terakhir dan 20 riwayat pemeriksaan.",
)
def get_tls_domain(
    domain_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TlsDomainDetailResponse]:
    return ApiResponse(data=_detail(db, _get_domain(db, domain_id)))


@router.patch(
    "/{domain_id}",
    response_model=ApiResponse[TlsDomainDetailResponse],
    summary="Ubah target TLS/SSL",
    description=(
        "Memperbarui label, host/port, status aktif, atau ambang warning. "
        "Perubahan host/port otomatis memicu pemeriksaan ulang."
    ),
    responses={403: {"description": "Tidak punya izin tls_domain:write"}},
)
async def update_tls_domain(
    domain_id: int,
    payload: TlsDomainUpdate,
    _: User = Depends(require_permission(Permission.TLS_DOMAIN_WRITE)),
    db: Session = Depends(get_db),
) -> ApiResponse[TlsDomainDetailResponse]:
    domain = _get_domain(db, domain_id)
    changes = payload.model_dump(exclude_unset=True)
    target_changed = "host" in changes or "port" in changes

    new_host = changes.get("host", domain.host)
    new_port = changes.get("port", domain.port)
    if target_changed:
        new_host = _validate(new_host, new_port)
        duplicate = tls_domain_repository.get_by_host_port(db, new_host, new_port)
        if duplicate is not None and duplicate.id != domain.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Host dan port tersebut sudah terdaftar"
            )
        domain.host = new_host
        domain.port = new_port
        domain.status = TlsDomainStatus.pending
        domain.days_remaining = None
        domain.expiry_date = None
        domain.issuer = None
        domain.subject = None
        domain.protocol = None
        domain.trusted = False
        domain.error_message = None
        domain.last_checked_at = None

    if "name" in changes:
        domain.name = changes["name"]
    if "enabled" in changes:
        domain.enabled = changes["enabled"]
    if "warning_days" in changes:
        domain.warning_days = changes["warning_days"]

    domain = tls_domain_repository.save(db, domain)
    if target_changed:
        domain = await _inspect(db, domain)
    elif (
        "warning_days" in changes
        and domain.days_remaining is not None
        and domain.status
        not in {
            TlsDomainStatus.expired,
            TlsDomainStatus.invalid,
            TlsDomainStatus.error,
            TlsDomainStatus.pending,
        }
    ):
        domain.status = (
            TlsDomainStatus.expiring
            if domain.days_remaining <= domain.warning_days
            else TlsDomainStatus.healthy
        )
        domain = tls_domain_repository.save(db, domain)
    return ApiResponse(data=_detail(db, domain))


@router.delete(
    "/{domain_id}",
    response_model=ApiResponse[dict[str, str]],
    summary="Hapus target TLS/SSL",
    responses={403: {"description": "Tidak punya izin tls_domain:write"}},
)
def delete_tls_domain(
    domain_id: int,
    _: User = Depends(require_permission(Permission.TLS_DOMAIN_WRITE)),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    domain = _get_domain(db, domain_id)
    tls_domain_repository.delete(db, domain)
    return ApiResponse(data={"message": "Domain TLS dihapus"})


@router.post(
    "/{domain_id}/check",
    response_model=ApiResponse[TlsDomainDetailResponse],
    summary="Periksa ulang sertifikat",
    description="Memaksa koneksi TLS baru dan menyimpan hasilnya ke riwayat.",
    responses={403: {"description": "Tidak punya izin tls_domain:write"}},
)
async def check_tls_domain(
    domain_id: int,
    _: User = Depends(require_permission(Permission.TLS_DOMAIN_WRITE)),
    db: Session = Depends(get_db),
) -> ApiResponse[TlsDomainDetailResponse]:
    domain = _get_domain(db, domain_id)
    domain = await _inspect(db, domain, force=True)
    return ApiResponse(data=_detail(db, domain))


@router.get(
    "/{domain_id}/checks",
    response_model=ApiResponse[list[TlsDomainCheckResponse]],
    summary="Riwayat pemeriksaan TLS",
)
def list_tls_domain_checks(
    domain_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[TlsDomainCheckResponse]]:
    _get_domain(db, domain_id)
    checks = tls_domain_repository.list_checks(db, domain_id, limit=limit)
    return ApiResponse(
        data=[TlsDomainCheckResponse.model_validate(check) for check in checks]
    )
