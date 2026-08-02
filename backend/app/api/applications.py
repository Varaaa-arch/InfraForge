"""
Router untuk manajemen aplikasi (Application Management — Task 3.2 & 3.10).

Endpoints:
  POST   /applications              → Daftarkan aplikasi baru ke dalam project
  GET    /applications              → Daftar semua aplikasi (filter opsional: ?project_id=)
  GET    /applications/{id}         → Detail konfigurasi aplikasi
  PATCH  /applications/{id}         → Update konfigurasi deployment aplikasi
  DELETE /applications/{id}         → Hapus aplikasi

Otorisasi:
  Semua endpoint membutuhkan JWT yang valid.
  User hanya dapat mengakses/memodifikasi aplikasi dari project yang dimilikinya.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_audit
from app.database.session import get_db
from app.models.application import Application
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
)
from app.schemas.common import MessageResponse
from app.schemas.response import ApiResponse
from app.services import application_service, project_service

router = APIRouter(prefix="/applications", tags=["applications"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_owned_project_or_404(project_id: int, current_user: User, db: Session) -> None:
    """Pastikan project_id ada dan dimiliki current_user. Raise 404 jika tidak."""
    project = project_service.get_project_by_id(db, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


def _get_owned_application_or_404(
    application_id: int, current_user: User, db: Session
) -> Application:
    """
    Ambil aplikasi berdasarkan ID, verifikasi bahwa project pemiliknya
    adalah milik current_user. Raise 404 jika tidak ditemukan atau bukan milik user.
    """
    app = application_service.get_application(db, application_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    # Verifikasi kepemilikan via project
    project = project_service.get_project_by_id(db, app.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    return app


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ApiResponse[ApplicationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Daftarkan aplikasi baru",
    description=(
        "Mendaftarkan aplikasi baru ke dalam sebuah project. "
        "Payload menyertakan konfigurasi deployment lengkap: URL repository, "
        "branch target, path Dockerfile, path docker-compose, dan build context. "
        "Status awal aplikasi adalah **idle**."
    ),
    responses={
        201: {"description": "Aplikasi berhasil dibuat"},
        404: {"description": "Project tidak ditemukan atau bukan milik user"},
        422: {"description": "Payload tidak valid (misal repository URL bukan https)"},
    },
)
def create_application(
    payload: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ApplicationResponse]:
    # Validasi project milik user yang login
    _get_owned_project_or_404(payload.project_id, current_user, db)

    app = application_service.create_application(db, payload)
    log_audit(
        "CREATE_APPLICATION",
        user=current_user.username,
        app=app.name,
        project_id=app.project_id,
    )
    return ApiResponse(data=ApplicationResponse.model_validate(app))


@router.get(
    "",
    response_model=ApiResponse[list[ApplicationResponse]],
    summary="Daftar semua aplikasi",
    description=(
        "Menampilkan daftar aplikasi milik user yang sedang login. "
        "Gunakan query parameter `project_id` untuk memfilter per project. "
        "Tanpa filter, semua aplikasi dari seluruh project user dikembalikan."
    ),
)
def list_applications(
    project_id: int | None = Query(
        default=None,
        description="Filter berdasarkan project ID (opsional)",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[ApplicationResponse]]:
    if project_id is not None:
        # Validasi project milik user
        _get_owned_project_or_404(project_id, current_user, db)
        apps = application_service.list_applications_by_project(db, project_id)
    else:
        # Ambil semua project milik user, lalu ambil semua aplikasinya
        projects = project_service.list_projects_for_owner(db, current_user.id)
        project_ids = [p.id for p in projects]
        apps = application_service.list_applications_for_owner(db, project_ids)

    return ApiResponse(data=[ApplicationResponse.model_validate(a) for a in apps])


@router.get(
    "/{application_id}",
    response_model=ApiResponse[ApplicationResponse],
    summary="Detail konfigurasi aplikasi",
    description=(
        "Menampilkan detail lengkap konfigurasi deployment sebuah aplikasi. "
        "Hanya pemilik project yang dapat mengakses endpoint ini."
    ),
)
def get_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ApplicationResponse]:
    app = _get_owned_application_or_404(application_id, current_user, db)
    return ApiResponse(data=ApplicationResponse.model_validate(app))


@router.patch(
    "/{application_id}",
    response_model=ApiResponse[ApplicationResponse],
    summary="Update konfigurasi deployment aplikasi",
    description=(
        "Mengupdate konfigurasi deployment aplikasi secara parsial. "
        "Semua field bersifat opsional — hanya field yang dikirim yang akan diubah. "
        "Field yang dapat diupdate: `name`, `repository`, `branch`, "
        "`dockerfile_path`, `compose_path`, `build_context`, `status`."
    ),
)
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ApplicationResponse]:
    app = _get_owned_application_or_404(application_id, current_user, db)
    updated = application_service.update_application(db, app, payload)
    log_audit(
        "UPDATE_APPLICATION",
        user=current_user.username,
        app=updated.name,
        application_id=updated.id,
    )
    return ApiResponse(data=ApplicationResponse.model_validate(updated))


@router.delete(
    "/{application_id}",
    response_model=ApiResponse[MessageResponse],
    summary="Hapus aplikasi",
    description="Menghapus aplikasi beserta seluruh konfigurasinya secara permanen.",
)
def delete_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    app = _get_owned_application_or_404(application_id, current_user, db)
    name = app.name
    application_service.delete_application(db, app)
    log_audit(
        "DELETE_APPLICATION",
        user=current_user.username,
        app=name,
        application_id=application_id,
    )
    return ApiResponse(data=MessageResponse(message="Application deleted successfully"))
