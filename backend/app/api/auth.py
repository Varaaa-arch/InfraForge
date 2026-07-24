from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_action
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest
from app.schemas.common import MessageResponse
from app.schemas.response import ApiResponse
from app.schemas.token import RefreshRequest, Token
from app.schemas.user import UserCreate, UserResponse
from app.services import auth_service, token_blocklist

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> ApiResponse[UserResponse]:
    if auth_service.get_user_by_username(db, payload.username):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username sudah dipakai")
    if auth_service.get_user_by_email(db, payload.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email sudah dipakai")

    user = auth_service.create_user(db, payload.username, payload.email, payload.password)
    log_action("REGISTER", user=user.username)
    return ApiResponse(data=UserResponse.model_validate(user))


@router.post("/login", response_model=ApiResponse[Token])
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> ApiResponse[Token]:
    user = auth_service.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        log_action("LOGIN_FAILED", user=form_data.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Username atau password salah")

    log_action("LOGIN", user=user.username)
    token = Token(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )
    return ApiResponse(data=token)


@router.post("/refresh", response_model=ApiResponse[Token])
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> ApiResponse[Token]:
    token_data = decode_token(payload.refresh_token)
    if not token_data or token_data.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token tidak valid")

    jti = token_data.get("jti")
    if jti and token_blocklist.is_blocklisted(jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token sudah tidak berlaku")

    user_id = token_data.get("sub")
    user = auth_service.get_user_by_id(db, int(user_id)) if user_id else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User tidak ditemukan")

    token = Token(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )
    return ApiResponse(data=token)


@router.post("/logout", response_model=ApiResponse[MessageResponse])
def logout(payload: RefreshRequest, db: Session = Depends(get_db)) -> ApiResponse[MessageResponse]:
    token_data = decode_token(payload.refresh_token)
    if not token_data or token_data.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token tidak valid")

    jti = token_data.get("jti")
    exp = token_data.get("exp")
    if jti and exp:
        remaining = int(exp - datetime.now(timezone.utc).timestamp())
        token_blocklist.blocklist_token(jti, remaining)

    user_id = token_data.get("sub")
    user = auth_service.get_user_by_id(db, int(user_id)) if user_id else None
    log_action("LOGOUT", user=user.username if user else "unknown")

    return ApiResponse(data=MessageResponse(message="Berhasil logout"))


@router.post("/change-password", response_model=ApiResponse[MessageResponse])
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    if not verify_password(payload.current_password, current_user.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password saat ini salah")

    auth_service.update_password(db, current_user, payload.new_password)
    log_action("CHANGE_PASSWORD", user=current_user.username)

    return ApiResponse(data=MessageResponse(message="Password berhasil diubah"))


@router.get("/me", response_model=ApiResponse[UserResponse])
def me(current_user: User = Depends(get_current_user)) -> ApiResponse[UserResponse]:
    return ApiResponse(data=UserResponse.model_validate(current_user))
