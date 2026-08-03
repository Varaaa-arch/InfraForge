"""
Router untuk Deployment Flow (Task 3.6 + Task 3.7).

Endpoints:
  POST  /deployments      → Picu deployment baru
  GET   /deployments      → List history dengan filter & pagination
  GET   /deployments/{id} → Detail satu deployment

Query params GET /deployments:
  application_id : filter per aplikasi (opsional)
  server_id      : filter per server target (opsional)
  status         : filter per status (pending/deploying/success/failed) (opsional)
  limit          : jumlah hasil (default 100, max 500)
  offset         : baris dilewati untuk pagination (default 0)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_audit
from app.database.session import get_db
from app.models.deployment import DeploymentStatus
from app.models.user import User
from app.schemas.deployment import DeploymentCreate, DeploymentResponse
from app.schemas.response import ApiResponse
from app.services import application_service, deployment_service, project_service

router = APIRouter(prefix="/deployments", tags=["deployments"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_owned_app_ids(current_user: User, db: Session) -> list[int]:
    """Kumpulkan semua application_id milik current_user (lintas project)."""
    projects = project_service.list_projects_for_owner(db, current_user.id)
    project_ids = [p.id for p in projects]
    apps = application_service.list_applications_for_owner(db, project_ids)
    return [a.id for a in apps]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ApiResponse[DeploymentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Picu deployment baru",
    description=(
        "Memicu deployment baru untuk sebuah aplikasi ke server target. "
        "Proses: clone repo → inject env vars → docker compose build + up. "
        "Field `branch` opsional — jika kosong, gunakan branch default dari "
        "konfigurasi aplikasi."
    ),
    responses={
        201: {"description": "Deployment berhasil dipicu"},
        404: {"description": "Aplikasi atau server tidak ditemukan / bukan milik user"},
        500: {"description": "Deployment gagal saat eksekusi (clone/compose error)"},
    },
)
def trigger_deployment(
    payload: DeploymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[DeploymentResponse]:
    owned_ids = _get_owned_app_ids(current_user, db)
    if payload.application_id not in owned_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    try:
        deployment = deployment_service.trigger_deployment(
            db=db,
            application_id=payload.application_id,
            server_id=payload.server_id,
            branch_override=payload.branch,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))

    log_audit(
        "TRIGGER_DEPLOYMENT",
        user=current_user.username,
        deployment_id=deployment.id,
        application_id=deployment.application_id,
        server_id=deployment.server_id,
    )
    return ApiResponse(data=DeploymentResponse.model_validate(deployment))


@router.get(
    "",
    response_model=ApiResponse[list[DeploymentResponse]],
    summary="List history deployment",
    description=(
        "Menampilkan history deployment milik user yang login. "
        "Semua filter bersifat opsional dan bisa dikombinasikan.\n\n"
        "- `application_id` — filter ke satu aplikasi tertentu\n"
        "- `server_id` — filter ke satu server target\n"
        "- `status` — `pending` | `deploying` | `success` | `failed`\n"
        "- `limit` / `offset` — pagination standar"
    ),
)
def list_deployments(
    application_id: int | None = Query(
        default=None,
        description="Filter berdasarkan application ID",
    ),
    server_id: int | None = Query(
        default=None,
        description="Filter berdasarkan server ID target deployment",
    ),
    status_filter: DeploymentStatus | None = Query(
        default=None,
        alias="status",
        description="Filter status: pending | deploying | success | failed",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Jumlah maksimal hasil (default: 100, max: 500)",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Jumlah baris yang dilewati untuk pagination (default: 0)",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[DeploymentResponse]]:
    owned_ids = _get_owned_app_ids(current_user, db)

    if application_id is not None:
        if application_id not in owned_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
        deployments = deployment_service.list_deployments_by_application(
            db,
            application_id,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    else:
        deployments = deployment_service.list_deployments(
            db,
            owned_ids,
            server_id=server_id,
            status=status_filter,
            limit=limit,
            offset=offset,
        )

    return ApiResponse(
        data=[DeploymentResponse.model_validate(d) for d in deployments]
    )


@router.get(
    "/{deployment_id}",
    response_model=ApiResponse[DeploymentResponse],
    summary="Detail deployment",
    description=(
        "Menampilkan detail satu deployment termasuk field `duration` (detik) "
        "dan `commit_sha`. Hanya pemilik aplikasi yang dapat mengaksesnya."
    ),
)
def get_deployment(
    deployment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[DeploymentResponse]:
    deployment = deployment_service.get_deployment(db, deployment_id)
    if deployment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment not found")

    owned_ids = _get_owned_app_ids(current_user, db)
    if deployment.application_id not in owned_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment not found")

    return ApiResponse(data=DeploymentResponse.model_validate(deployment))
