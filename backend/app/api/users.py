from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_audit
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.response import ApiResponse
from app.schemas.user import UserResponse, UserUpdate
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
