"""API policy resource & auto-healing per container."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.permissions import require_permission
from app.core.roles import Permission
from app.database.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.repositories import container_policy_repository
from app.schemas.container_policy import (
    AutoHealWorkerStatus,
    ContainerIncidentResponse,
    ContainerPolicyDetail,
    ContainerPolicyListResponse,
    ContainerPolicyMutationResult,
    ContainerPolicyResponse,
    ContainerPolicyUpsert,
)
from app.schemas.response import ApiResponse
from app.services import (
    auto_heal_service,
    container_policy_service,
    container_service,
)

router = APIRouter(tags=["container-policies"])


def _handle_runtime(exc: RuntimeError) -> HTTPException:
    msg = str(exc)
    if "tidak ditemukan" in msg.lower():
        return HTTPException(status.HTTP_404_NOT_FOUND, msg)
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, msg)


def _detail(container_id: str, db: Session) -> ContainerPolicyDetail:
    container, attrs, _name, policy = container_policy_service.get_policy_for_container(
        db, container_id
    )
    return ContainerPolicyDetail(
        container_id=str(getattr(container, "short_id", container_id)),
        container_name=str(getattr(container, "name", container_id)),
        compose_project=container_service._extract_compose_labels(attrs)[0],
        compose_service=container_service._extract_compose_labels(attrs)[1],
        status=str(getattr(container, "status", "")),
        health=container_service._extract_health(attrs),
        policy=ContainerPolicyResponse.model_validate(policy) if policy else None,
        effective=container_policy_service.get_effective_limits(attrs),
    )


@router.get(
    "/containers/{container_id}/policy",
    response_model=ApiResponse[ContainerPolicyDetail],
    summary="Policy resource container",
    description=(
        "Menampilkan policy CPU/memory, restart policy, dan auto-healing untuk "
        "container, beserta limit yang sedang aktif di Docker."
    ),
)
def get_container_policy(
    container_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ContainerPolicyDetail]:
    try:
        return ApiResponse(data=_detail(container_id, db))
    except RuntimeError as exc:
        raise _handle_runtime(exc)


@router.put(
    "/containers/{container_id}/policy",
    response_model=ApiResponse[ContainerPolicyMutationResult],
    summary="Simpan policy resource container",
    description=(
        "Menyimpan limit CPU (cores/quota/period), memory limit, restart policy, "
        "dan pengaturan auto-healing. Dengan `apply_now=true` limit langsung "
        "diterapkan ke container running."
    ),
    responses={
        403: {"description": "Tidak punya izin container:lifecycle"},
        404: {"description": "Container tidak ditemukan"},
        502: {"description": "Policy tersimpan tetapi penerapan ke Docker gagal"},
    },
)
def upsert_container_policy(
    container_id: str,
    payload: ContainerPolicyUpsert,
    _: User = Depends(require_permission(Permission.CONTAINER_LIFECYCLE)),
    db: Session = Depends(get_db),
) -> ApiResponse[ContainerPolicyMutationResult]:
    try:
        policy, effective = container_policy_service.upsert_policy(
            db, container_id, payload
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except RuntimeError as exc:
        if "tidak ditemukan" in str(exc).lower():
            raise _handle_runtime(exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Policy tersimpan tetapi penerapan ke Docker gagal: {exc}",
        ) from exc

    return ApiResponse(
        data=ContainerPolicyMutationResult(
            policy=ContainerPolicyResponse.model_validate(policy),
            effective=effective,
            message="Policy container disimpan",
        )
    )


@router.delete(
    "/containers/{container_id}/policy",
    response_model=ApiResponse[dict[str, object]],
    summary="Hapus policy resource container",
    description=(
        "Menghapus policy tersimpan. Limit CPU/memory yang sudah aktif di "
        "Docker tetap berlaku sampai container dibuat ulang (Engine API "
        "menganggap nilai 0 sebagai \"tanpa perubahan\")."
    ),
)
def delete_container_policy(
    container_id: str,
    _: User = Depends(require_permission(Permission.CONTAINER_LIFECYCLE)),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, object]]:
    try:
        name = container_policy_service.delete_policy(db, container_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except RuntimeError as exc:
        raise _handle_runtime(exc)

    return ApiResponse(
        data={
            "message": (
                f"Policy {name} dihapus. Limit yang sudah aktif di Docker "
                "tetap berlaku sampai container dibuat ulang."
            ),
            "container_name": name,
        }
    )


@router.get(
    "/container-policies",
    response_model=ApiResponse[ContainerPolicyListResponse],
    summary="Daftar policy container",
    description=(
        "Menampilkan semua policy resource/auto-healing beserta status worker "
        "health polling."
    ),
)
def list_container_policies(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ContainerPolicyListResponse]:
    policies = container_policy_repository.list_all(db)
    return ApiResponse(
        data=ContainerPolicyListResponse(
            items=[
                ContainerPolicyResponse.model_validate(policy) for policy in policies
            ],
            worker=AutoHealWorkerStatus.model_validate(
                auto_heal_service.get_worker_status()
            ),
        )
    )


@router.get(
    "/container-policies/incidents",
    response_model=ApiResponse[list[ContainerIncidentResponse]],
    summary="Insiden auto-healing",
    description=(
        "Riwayat insiden auto-healing (unhealthy, auto-restart, recovered) dari "
        "audit log. Filter opsional berdasarkan nama container."
    ),
)
def list_container_incidents(
    container_name: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[ContainerIncidentResponse]]:
    stmt = select(AuditLog).where(
        AuditLog.action.in_(auto_heal_service.INCIDENT_ACTIONS)
    )
    if container_name:
        stmt = stmt.where(AuditLog.resource_id == container_name)
    rows = list(
        db.execute(stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)).scalars()
    )
    return ApiResponse(
        data=[
            ContainerIncidentResponse(
                id=row.id,
                action=row.action,
                container_name=row.resource_id,
                created_at=row.created_at,
                details=row.details,
            )
            for row in rows
        ]
    )
