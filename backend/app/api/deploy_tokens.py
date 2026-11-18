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
from app.models.deployment_token import DeploymentToken
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.deployment_token import (
    DeployWebhookResponse,
    DeploymentScheduledItem,
    DeploymentTokenCreate,
    DeploymentTokenCreated,
    DeploymentTokenResponse,
    DeploymentTriggerRequest,
    DeploymentTriggerResponse,
)
from app.schemas.response import ApiResponse
from app.services import (
    deployment_notification_service,
    deployment_queue,
    deployment_token_service,
    deployment_webhook_service,
    project_service,
)

router = APIRouter(
    prefix="/projects/{project_id}/deploy-tokens",
    tags=["deploy-tokens"],
)
public_router = APIRouter(prefix="/deploy", tags=["deploy-trigger"])
webhook_router = APIRouter(prefix="/v1/deploy", tags=["deploy-webhook"])


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

    try:
        record, token = deployment_token_service.create_token(
            db,
            project_id=project_id,
            created_by=current_user.id,
            name=payload.name,
            expires_in_days=payload.expires_in_days,
            application_id=payload.application_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

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
        tag=body.tag,
    )

    request.state.audit_username = f"deploy-token:{record.name}"
    request.state.audit_resource_id = str(record.id)
    request.state.audit_details = {
        "source": "ci",
        "outcome": "scheduled",
        "application_id": str(application.id),
        "branch": deployment.branch,
    }

    background_tasks.add_task(
        deployment_notification_service.notify_queued,
        deployment.id,
    )
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
            tag=deployment.tag,
            status=deployment.status,
            message=f"Deployment #{deployment.id} dijadwalkan",
        )
    )


# ---------------------------------------------------------------------------
# Endpoint publik: webhook receiver per-project (GitHub/GitLab/CI)
# ---------------------------------------------------------------------------

def _audit_webhook(
    request: Request,
    record: DeploymentToken | None,
    source: str,
    outcome: str,
    parsed: deployment_webhook_service.ParsedWebhook | None = None,
    **extra: object,
) -> None:
    """Isi state audit middleware tanpa pernah menyertakan token mentah."""
    request.state.audit_path = "/v1/deploy/webhook/[redacted]"
    if record is not None:
        request.state.audit_username = f"deploy-token:{record.name}"
        request.state.audit_resource_id = str(record.id)

    details: dict[str, str] = {"source": source}
    if parsed is not None:
        details.update(deployment_webhook_service.audit_details(parsed))
    details["outcome"] = outcome
    for key, value in extra.items():
        if value is None:
            continue
        details[key] = str(value)
    request.state.audit_details = details


def _webhook_response(
    *,
    accepted: bool,
    message: str,
    parsed: deployment_webhook_service.ParsedWebhook,
    scheduled: list[deployment_webhook_service.ScheduledDeployment] | None = None,
    skipped: list[int] | None = None,
    deployment_ids: list[int] | None = None,
    branch: str | None = None,
) -> ApiResponse[DeployWebhookResponse]:
    scheduled = scheduled or []
    items = [
        DeploymentScheduledItem(
            deployment_id=item.deployment.id,
            application_id=item.application.id,
            application_name=item.application.name,
            branch=item.deployment.branch,
            tag=item.deployment.tag,
            status=item.deployment.status,
        )
        for item in scheduled
    ]
    ids = (
        deployment_ids
        if deployment_ids is not None
        else [item.deployment.id for item in scheduled]
    )
    return ApiResponse(
        data=DeployWebhookResponse(
            accepted=accepted,
            message=message,
            source=parsed.source,
            event=parsed.event,
            branch=branch or parsed.branch,
            deployment_ids=ids,
            deployments=items,
            skipped_application_ids=skipped or [],
        )
    )


@webhook_router.post(
    "/webhook/{token}",
    response_model=ApiResponse[DeployWebhookResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Webhook receiver deployment per-project",
    description=(
        "Endpoint publik untuk GitHub Actions, GitLab CI, atau webhook native "
        "GitHub/GitLab. Autentikasi memakai deployment token project pada path.\n\n"
        "- **GitHub native**: kirim `X-GitHub-Event` + `X-Hub-Signature-256`; "
        "secret webhook = token deployment.\n"
        "- **GitLab native**: kirim `X-Gitlab-Event` + `X-Gitlab-Token`; "
        "secret token = token deployment.\n"
        "- **CI sederhana**: tanpa header event, body opsional "
        "`{application_id, branch, server_id}`.\n\n"
        "Deployment dijalankan di background; response 202 berisi daftar "
        "`deployment_ids`."
    ),
    responses={
        202: {"description": "Event diterima/diabaikan tanpa retry"},
        400: {"description": "Payload bukan JSON yang valid"},
        401: {"description": "Signature GitHub / secret GitLab tidak valid"},
        404: {"description": "Token tidak valid, sudah dicabut, atau kedaluwarsa"},
        409: {"description": "Aplikasi target sedang deploy (mode CI sederhana)"},
        422: {"description": "Target CI sederhana ambigu atau tidak ditemukan"},
    },
)
async def deployment_webhook(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ApiResponse[DeployWebhookResponse]:
    request.state.audit_path = "/v1/deploy/webhook/[redacted]"
    source = deployment_webhook_service.detect_source(request.headers)

    record = deployment_token_service.find_active_by_token(db, token)
    if record is None:
        _audit_webhook(request, None, source, "invalid_token")
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Token deployment tidak valid, sudah dicabut, atau kedaluwarsa",
        )

    request.state.audit_username = f"deploy-token:{record.name}"
    request.state.audit_resource_id = str(record.id)

    raw_body = await request.body()
    try:
        parsed = deployment_webhook_service.parse_webhook_request(
            request.headers, raw_body, token
        )
    except deployment_webhook_service.InvalidWebhookSignature as exc:
        _audit_webhook(request, record, source, "invalid_signature")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
    except deployment_webhook_service.InvalidWebhookPayload as exc:
        _audit_webhook(request, record, source, "invalid_payload")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    if parsed.delivery_id:
        existing_id = deployment_queue.is_duplicate_delivery(parsed.delivery_id)
        if existing_id is not None:
            _audit_webhook(
                request,
                record,
                parsed.source,
                "duplicate",
                parsed,
                deployment_ids=existing_id,
            )
            return _webhook_response(
                accepted=False,
                message=f"Delivery {parsed.delivery_id} sudah pernah diproses",
                parsed=parsed,
                deployment_ids=[existing_id],
            )

    if parsed.event is not None and parsed.event.lower() != "push":
        _audit_webhook(request, record, parsed.source, "ignored_event", parsed)
        return _webhook_response(
            accepted=False,
            message=f"Event '{parsed.event}' tidak diproses (hanya push)",
            parsed=parsed,
        )

    try:
        _project, server, applications = (
            deployment_webhook_service.resolve_applications(db, record, parsed)
        )
    except ValueError as exc:
        if parsed.source == "ci":
            _audit_webhook(request, record, parsed.source, "invalid_target", parsed)
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
        _audit_webhook(request, record, parsed.source, "no_target", parsed)
        return _webhook_response(
            accepted=False,
            message=str(exc),
            parsed=parsed,
        )

    if not applications:
        _audit_webhook(request, record, parsed.source, "no_match", parsed)
        reason = (
            "Ref event bukan branch push"
            if parsed.branch is None
            else (
                "Tidak ada aplikasi yang cocok untuk repository/branch "
                "pada event ini"
            )
        )
        return _webhook_response(
            accepted=False,
            message=reason,
            parsed=parsed,
        )

    skipped: list[int] = []
    for application in applications:
        running_id = deployment_queue.get_running_deployment_id(application.id)
        if running_id is None:
            continue
        if parsed.source == "ci":
            _audit_webhook(
                request,
                record,
                parsed.source,
                "conflict",
                parsed,
                application_ids=application.id,
                running_deployment_id=running_id,
            )
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                (
                    f"Aplikasi {application.id} sedang dalam proses deployment "
                    f"(deployment_id={running_id}). Tunggu hingga selesai."
                ),
            )
        skipped.append(application.id)

    active = [
        application for application in applications if application.id not in skipped
    ]
    scheduled = deployment_webhook_service.trigger_applications(
        db,
        record,
        active,
        server,
        branch=parsed.branch,
        tag=parsed.request.tag if parsed.request else None,
    )

    if not scheduled:
        _audit_webhook(
            request,
            record,
            parsed.source,
            "locked",
            parsed,
            application_ids=",".join(str(item) for item in skipped),
        )
        return _webhook_response(
            accepted=False,
            message="Semua aplikasi target sedang dalam proses deployment",
            parsed=parsed,
            skipped=skipped,
        )

    if parsed.delivery_id:
        deployment_queue.mark_delivery_processed(
            parsed.delivery_id, scheduled[0].deployment.id
        )

    deployment_ids = [item.deployment.id for item in scheduled]
    application_ids = [item.application.id for item in scheduled]
    _audit_webhook(
        request,
        record,
        parsed.source,
        "scheduled" if not skipped else "partial",
        parsed,
        application_ids=",".join(str(item) for item in application_ids),
        deployment_ids=",".join(str(item) for item in deployment_ids),
        skipped_application_ids=",".join(str(item) for item in skipped) or None,
        branch=scheduled[0].deployment.branch,
    )

    for item in scheduled:
        background_tasks.add_task(
            deployment_notification_service.notify_queued,
            item.deployment.id,
        )
    for item in scheduled:
        background_tasks.add_task(
            deployment_queue.run_deployment_background,
            deployment_id=item.deployment.id,
            application_id=item.application.id,
            server_id=item.server.id,
        )

    message = f"{len(scheduled)} deployment dijadwalkan"
    if skipped:
        message += f"; {len(skipped)} aplikasi di-skip karena sedang deploy"
    return _webhook_response(
        accepted=True,
        message=message,
        parsed=parsed,
        scheduled=scheduled,
        skipped=skipped,
        branch=scheduled[0].deployment.branch,
    )
