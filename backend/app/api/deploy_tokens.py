"""Router deployment token (CI/CD) per project + endpoint publik trigger.

Endpoint manajemen (butuh login, hanya owner project):
  POST   /projects/{project_id}/deploy-tokens          → buat token (plaintext sekali)
  GET    /projects/{project_id}/deploy-tokens          → list metadata token
  DELETE /projects/{project_id}/deploy-tokens/{id}     → cabut token

Endpoint publik (tanpa login, autentikasi via token):
  POST   /deploy/trigger/{token}                       → jadwalkan deployment

Token plaintext hanya ditampilkan sekali saat dibuat; database hanya
menyimpan hash SHA-256. Endpoint publik mengembalikan 202 Accepted dan
menjalankan deployment di background (pola yang sama dengan webhook GitHub).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.permissions import require_permission
from app.core.roles import Permission
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.deployment_token import (
    DeploymentTokenCreate,
    DeploymentTokenCreated,
    DeploymentTokenResponse,
    DeploymentTriggerRequest,
    DeploymentTriggerResponse,
)
from app.schemas.response import ApiResponse
from app.services import deployment_queue, deployment_token_service, project_service

router = APIRouter(
    prefix="/projects/{project_id}/deploy-tokens",
    tags=["deploy-tokens"],
)
public_router = APIRouter(prefix="/deploy", tags=["deploy-trigger"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _require_owned_project(
    project_id: int, current_user: User, db: Session
) -> None:
    """Raise 404 jika project tidak ada atau bukan milik current_user."""
    project = project_service.get_project_by_id(db, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


# ---------------------------------------------------------------------------
# Manajemen token (login + owner project)
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ApiResponse[DeploymentTokenCreated],
    status_code=status.HTTP_201_CREATED,
    summary="Buat deployment token project",
    description=(
        "Membuat token CI/CD baru untuk sebuah project. "
        "**Token plaintext hanya dikembalikan sekali** pada response ini — "
        "simpan di secret GitHub Actions/webhook. Database hanya menyimpan "
        "hash SHA-256. Token terikat ke project dan dapat memicu deployment "
        "lewat `POST /deploy/trigger/{token}`."
    ),
    responses={
        201: {"description": "Token berhasil dibuat (plaintext hanya di response ini)"},
        403: {"description": "Peran user tidak memiliki izin deploy"},
        404: {"description": "Project tidak ditemukan atau bukan milik user"},
    },
)
def create_deploy_token(
    project_id: int,
    payload: DeploymentTokenCreate,
    current_user: User = Depends(require_permission(Permission.DEPLOY)),
    db: Session = Depends(get_db),
) -> ApiResponse[DeploymentTokenCreated]:
    _require_owned_project(project_id, current_user, db)

    record, token = deployment_token_service.create_token(
        db,
        project_id=project_id,
        created_by=current_user.id,
        name=payload.name,
        expires_in_days=payload.expires_in_days,
    )

    base = DeploymentTokenResponse.model_validate(record)
    return ApiResponse(data=DeploymentTokenCreated(**base.model_dump(), token=token))


@router.get(
    "",
    response_model=ApiResponse[list[DeploymentTokenResponse]],
    summary="List deployment token project",
    description=(
        "Menampilkan metadata token deployment milik project (prefix, masa "
        "berlaku, terakhir dipakai, status cabut). Token plaintext maupun "
        "hash tidak pernah dikembalikan."
    ),
    responses={
        404: {"description": "Project tidak ditemukan atau bukan milik user"},
    },
)
def list_deploy_tokens(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[DeploymentTokenResponse]]:
    _require_owned_project(project_id, current_user, db)
    tokens = deployment_token_service.list_tokens(db, project_id)
    return ApiResponse(
        data=[DeploymentTokenResponse.model_validate(token) for token in tokens]
    )


@router.delete(
    "/{token_id}",
    response_model=ApiResponse[MessageResponse],
    summary="Cabut deployment token",
    description=(
        "Mencabut token sehingga tidak bisa lagi memicu deployment. "
        "Deployment yang sudah berjalan tidak dibatalkan."
    ),
    responses={
        404: {"description": "Project atau token tidak ditemukan"},
    },
)
def revoke_deploy_token(
    project_id: int,
    token_id: int,
    current_user: User = Depends(require_permission(Permission.DEPLOY)),
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    _require_owned_project(project_id, current_user, db)

    token = deployment_token_service.get_token(db, project_id, token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token tidak ditemukan")

    if token.revoked_at is None:
        deployment_token_service.revoke_token(db, token)

    return ApiResponse(data=MessageResponse(message="Token deployment dicabut"))


# ---------------------------------------------------------------------------
# Endpoint publik: trigger deployment via token
# ---------------------------------------------------------------------------

@public_router.post(
    "/trigger/{token}",
    response_model=ApiResponse[DeploymentTriggerResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger deployment via deployment token",
    description=(
        "Endpoint publik untuk CI/CD (GitHub Actions, GitLab CI, curl). "
        "Autentikasi memakai deployment token project (`dt_...`) pada path. "
        "Deployment dijadwalkan di background dan langsung mengembalikan 202 "
        "berisi `deployment_id`; status terbaru dapat dilihat di riwayat "
        "deployment project.\n\n"
        "Untuk project dengan lebih dari satu aplikasi, sertakan "
        "`application_id` di body."
    ),
    responses={
        202: {"description": "Deployment dijadwalkan di background"},
        404: {"description": "Token tidak valid, sudah dicabut, atau kedaluwarsa"},
        409: {"description": "Aplikasi sedang dalam proses deployment"},
        422: {"description": "Target aplikasi/server ambigu atau tidak ditemukan"},
    },
)
def trigger_deployment_by_token(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: DeploymentTriggerRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[DeploymentTriggerResponse]:
    request.state.audit_path = "/deploy/trigger/[redacted]"

    record = deployment_token_service.find_active_by_token(db, token)
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Token deployment tidak valid, sudah dicabut, atau kedaluwarsa",
        )

    body = payload or DeploymentTriggerRequest()

    try:
        _project, application, server = deployment_token_service.resolve_target(
            db,
            record,
            application_id=body.application_id,
            server_id=body.server_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    running_id = deployment_queue.get_running_deployment_id(application.id)
    if running_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                f"Aplikasi {application.id} sedang dalam proses deployment "
                f"(deployment_id={running_id}). Tunggu hingga selesai."
            ),
        )

    deployment = deployment_token_service.trigger_deployment(
        db,
        record,
        application,
        server,
        branch=body.branch,
    )

    request.state.audit_username = f"deploy-token:{record.name}"
    request.state.audit_resource_id = str(record.id)
    request.state.audit_details = {
        "application_id": str(application.id),
        "branch": deployment.branch,
    }

    background_tasks.add_task(
        deployment_queue.run_deployment_background,
        deployment_id=deployment.id,
        application_id=application.id,
        server_id=server.id,
    )

    return ApiResponse(
        data=DeploymentTriggerResponse(
            deployment_id=deployment.id,
            application_id=application.id,
            application_name=application.name,
            branch=deployment.branch,
            status=deployment.status,
            message=f"Deployment #{deployment.id} dijadwalkan",
        )
    )
