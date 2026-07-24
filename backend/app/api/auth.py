from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_audit
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.database.session import get_db
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.token import RefreshRequest, Token
from app.schemas.user import UserCreate, UserResponse
from app.services import auth_service

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
    log_audit("REGISTER", user=user.username)
    return ApiResponse(data=UserResponse.model_validate(user))


@router.post("/login", response_model=ApiResponse[Token])
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> ApiResponse[Token]:
    user = auth_service.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        log_audit("LOGIN_FAILED", user=form_data.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Username atau password salah")

    log_audit("LOGIN", user=user.username)
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

    user_id = token_data.get("sub")
    user = auth_service.get_user_by_id(db, int(user_id)) if user_id else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User tidak ditemukan")

    log_audit("REFRESH_TOKEN", user=user.username)
    token = Token(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )
    return ApiResponse(data=token)


@router.get("/me", response_model=ApiResponse[UserResponse])
def me(current_user: User = Depends(get_current_user)) -> ApiResponse[UserResponse]:
    return ApiResponse(data=UserResponse.model_validate(current_user))
