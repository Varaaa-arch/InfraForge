from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_audit
from app.core.permissions import require_permission
from app.core.roles import Permission, Role
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.response import ApiResponse
from app.schemas.user import AdminUserUpdate, UserResponse, UserUpdate
from app.services import auth_service, user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=ApiResponse[UserResponse])
def get_profile(current_user: User = Depends(get_current_user)) -> ApiResponse[UserResponse]:
    return ApiResponse(data=UserResponse.model_validate(current_user))


@router.patch("/me", response_model=ApiResponse[UserResponse])
def update_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[UserResponse]:
    if payload.username and payload.username != current_user.username:
        if auth_service.get_user_by_username(db, payload.username):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username sudah dipakai")

    if payload.email and payload.email != current_user.email:
        if auth_service.get_user_by_email(db, payload.email):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email sudah dipakai")

    updated_user = user_service.update_profile(
        db,
        current_user,
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
    )
    log_audit("UPDATE_PROFILE", user=updated_user.username)
    return ApiResponse(data=UserResponse.model_validate(updated_user))


@router.delete("/me", response_model=ApiResponse[MessageResponse])
def delete_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    username = current_user.username
    user_service.deactivate_user(db, current_user)
    log_audit("DEACTIVATE_ACCOUNT", user=username)
    return ApiResponse(data=MessageResponse(message="Akun berhasil dinonaktifkan"))


@router.get(
    "",
    response_model=ApiResponse[list[UserResponse]],
    summary="List semua user (admin)",
    description=(
        "Menampilkan seluruh akun pengguna beserta peran dan status aktifnya. "
        "Hanya dapat diakses oleh peran **admin**."
    ),
)
def list_users(
    limit: int = Query(default=100, ge=1, le=500, description="Jumlah maksimal hasil"),
    offset: int = Query(default=0, ge=0, description="Jumlah baris yang dilewati"),
    _: User = Depends(require_permission(Permission.USER_MANAGE)),
    db: Session = Depends(get_db),
) -> ApiResponse[list[UserResponse]]:
    users = user_service.list_users(db, limit=limit, offset=offset)
    return ApiResponse(data=[UserResponse.model_validate(user) for user in users])


@router.patch(
    "/{user_id}",
    response_model=ApiResponse[UserResponse],
    summary="Ubah peran / status user (admin)",
    description=(
        "Mengubah peran (`admin` | `developer` | `viewer`) dan/atau status aktif akun lain. "
        "Admin tidak dapat mengubah akunnya sendiri, dan admin terakhir tidak dapat "
        "diturunkan atau dinonaktifkan."
    ),
    responses={
        400: {"description": "Perubahan ditolak (akun sendiri / admin terakhir)"},
        403: {"description": "Bukan admin"},
        404: {"description": "User tidak ditemukan"},
    },
)
def admin_update_user(
    user_id: int,
    payload: AdminUserUpdate,
    current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    db: Session = Depends(get_db),
) -> ApiResponse[UserResponse]:
    target = auth_service.get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User tidak ditemukan")

    if target.id == current_user.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Tidak dapat mengubah peran/status akun sendiri",
        )

    new_role = payload.role.value if payload.role is not None else None
    is_demoting_last_admin = (
        target.role == Role.ADMIN.value
        and (
            (new_role is not None and new_role != Role.ADMIN.value)
            or payload.is_active is False
        )
        and user_service.count_admins(db) <= 1
    )
    if is_demoting_last_admin:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Tidak dapat menurunkan atau menonaktifkan admin terakhir",
        )

    updated = user_service.update_user_admin(
        db, target, role=new_role, is_active=payload.is_active
    )
    log_audit(
        "UPDATE_USER",
        user=current_user.username,
        target=updated.username,
        role=updated.role,
        is_active=updated.is_active,
    )
    return ApiResponse(data=UserResponse.model_validate(updated))
