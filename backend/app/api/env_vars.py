"""
Router untuk manajemen environment variables per project.

Endpoint dikelompokkan di bawah /projects/{project_id}/env sehingga
URL secara eksplisit mencerminkan kepemilikan (env var adalah milik project).

Endpoints:
  POST   /projects/{project_id}/env           → Bulk upsert env vars
  GET    /projects/{project_id}/env           → List env vars (masked) + status re-deploy
  GET    /projects/{project_id}/env/{env_id}  → Detail env var (value plaintext)
  PATCH  /projects/{project_id}/env/{env_id}  → Ubah nilai satu env var
  DELETE /projects/{project_id}/env/{env_id}  → Hapus satu env var

Otorisasi:
  Semua endpoint membutuhkan token JWT yang valid.
  User hanya bisa mengakses env vars dari project miliknya sendiri.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_audit
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.env_var import (
    EnvVarBulkCreate,
    EnvVarListResponse,
    EnvVarMaskedResponse,
    EnvVarResponse,
    EnvVarUpdate,
)
from app.schemas.response import ApiResponse
from app.services import env_var_service, project_service

router = APIRouter(prefix="/projects/{project_id}/env", tags=["env-vars"])


# ---------------------------------------------------------------------------
# Helper: pastikan project ada dan milik user yang login
# ---------------------------------------------------------------------------

def _require_owned_project(
    project_id: int, current_user: User, db: Session
) -> None:
    """Raise 404 jika project tidak ada atau bukan milik current_user."""
    project = project_service.get_project_by_id(db, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ApiResponse[dict[str, object]],
    status_code=status.HTTP_200_OK,
    summary="Bulk upsert environment variables",
    description=(
        "Menambahkan atau memperbarui beberapa environment variables sekaligus untuk "
        "sebuah project. Operasi bersifat **upsert**: jika key sudah ada, value-nya "
        "diperbarui; jika belum ada, env var baru dibuat. "
        "Value dienkripsi otomatis dengan Fernet sebelum disimpan ke database. "
        "Response berisi ringkasan (jumlah created/updated) dan data lengkap tiap env var."
    ),
    responses={
        200: {"description": "Upsert berhasil, beserta ringkasan dan daftar env vars"},
        404: {"description": "Project tidak ditemukan atau bukan milik user"},
        422: {"description": "Format key tidak valid atau value kosong"},
    },
)
def bulk_upsert_env_vars(
    project_id: int,
    payload: EnvVarBulkCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, object]]:
    _require_owned_project(project_id, current_user, db)
    env_vars, summary = env_var_service.bulk_upsert(db, project_id, payload)
    log_audit(
        "BULK_UPSERT_ENV_VARS",
        user=current_user.username,
        project_id=project_id,
        total=summary.total,
    )
    return ApiResponse(
        data={
            "summary": summary.model_dump(),
            "env_vars": [ev.model_dump() for ev in env_vars],
        }
    )


@router.get(
    "",
    response_model=ApiResponse[EnvVarListResponse],
    summary="List environment variables (masked)",
    description=(
        "Menampilkan daftar seluruh environment variables milik project. "
        "Value disamarkan (hanya 3 karakter pertama yang terlihat + `****`) "
        "untuk mencegah paparan credential di tampilan list/dashboard. "
        "Respons juga membawa `last_deployment_at` dan flag `pending_redeploy` "
        "per variabel — `true` berarti variabel diubah setelah deployment "
        "terakhir sehingga container yang jalan belum memakai nilai baru. "
        "Gunakan endpoint `GET /env/{id}` untuk melihat value lengkap."
    ),
)
def list_env_vars(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EnvVarListResponse]:
    _require_owned_project(project_id, current_user, db)
    data = env_var_service.list_env_vars_with_status(db, project_id)
    return ApiResponse(data=data)


@router.patch(
    "/{env_id}",
    response_model=ApiResponse[EnvVarMaskedResponse],
    summary="Ubah nilai environment variable",
    description=(
        "Memperbarui nilai satu environment variable milik project. "
        "Key tidak dapat diubah (gunakan bulk upsert dengan key baru lalu hapus "
        "key lama). Value baru dienkripsi ulang sebelum disimpan. "
        "Respons mengembalikan nilai dalam bentuk masked."
    ),
    responses={
        200: {"description": "Nilai berhasil diperbarui"},
        404: {"description": "Environment variable tidak ditemukan"},
        422: {"description": "Value kosong atau mengandung karakter terlarang"},
    },
)
def update_env_var(
    project_id: int,
    env_id: int,
    payload: EnvVarUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EnvVarMaskedResponse]:
    _require_owned_project(project_id, current_user, db)
    env_var = env_var_service.update_env_var(db, project_id, env_id, payload.value)
    if env_var is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Environment variable not found")
    log_audit(
        "UPDATE_ENV_VAR",
        user=current_user.username,
        project_id=project_id,
        env_id=env_id,
        key=env_var.key,
    )
    return ApiResponse(data=env_var)


@router.get(
    "/{env_id}",
    response_model=ApiResponse[EnvVarResponse],
    summary="Detail environment variable (plaintext)",
    description=(
        "Menampilkan detail satu environment variable beserta nilai plaintext-nya "
        "(sudah didekripsi). Endpoint ini setara dengan fitur 'Reveal value' di UI."
    ),
)
def get_env_var(
    project_id: int,
    env_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EnvVarResponse]:
    _require_owned_project(project_id, current_user, db)
    env_var = env_var_service.get_env_var(db, project_id, env_id)
    if env_var is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Environment variable not found")
    log_audit(
        "REVEAL_ENV_VAR",
        user=current_user.username,
        project_id=project_id,
        env_id=env_id,
        key=env_var.key,
    )
    return ApiResponse(data=env_var)


@router.delete(
    "/{env_id}",
    response_model=ApiResponse[MessageResponse],
    summary="Hapus environment variable",
    description="Menghapus satu environment variable dari project secara permanen.",
)
def delete_env_var(
    project_id: int,
    env_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    _require_owned_project(project_id, current_user, db)
    deleted = env_var_service.delete_env_var(db, project_id, env_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Environment variable not found")
    log_audit(
        "DELETE_ENV_VAR",
        user=current_user.username,
        project_id=project_id,
        env_id=env_id,
    )
    return ApiResponse(data=MessageResponse(message="Environment variable deleted successfully"))
