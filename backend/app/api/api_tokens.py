"""Router Personal Access Token (CLI / CI-CD).

Token hanya ditampilkan sekali saat dibuat. Setelah itu UI/API hanya
memperlihatkan prefix-nya.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_audit
from app.database.session import get_db
from app.models.user import User
from app.schemas.api_token import ApiTokenCreate, ApiTokenCreated, ApiTokenResponse
from app.schemas.common import MessageResponse
from app.schemas.response import ApiResponse
from app.services import api_token_service

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])


@router.post(
    "",
    response_model=ApiResponse[ApiTokenCreated],
    status_code=status.HTTP_201_CREATED,
    summary="Buat personal access token",
    description=(
        "Membuat token baru untuk akses CLI/CI-CD. "
        "**Token plaintext hanya dikembalikan sekali** pada response ini — "
        "simpan di secret manager. Database hanya menyimpan hash SHA-256."
    ),
)
def create_api_token(
    payload: ApiTokenCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ApiTokenCreated]:
    scopes: list[str] | None = None
    if payload.scopes is not None:
        scopes = list(dict.fromkeys(payload.scopes))
        if not scopes:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Minimal satu scope harus dipilih",
            )

    record, token = api_token_service.create_token(
        db,
        user_id=current_user.id,
        name=payload.name,
        scopes=scopes,
        expires_in_days=payload.expires_in_days,
    )
    log_audit(
        "CREATE_API_TOKEN",
        user=current_user.username,
        token_id=record.id,
        token_name=record.name,
    )

    base = ApiTokenResponse.model_validate(record)
    return ApiResponse(data=ApiTokenCreated(**base.model_dump(), token=token))


@router.get(
    "",
    response_model=ApiResponse[list[ApiTokenResponse]],
    summary="List personal access token milik sendiri",
    description=(
        "Menampilkan metadata token milik user yang login (prefix, scope, "
        "terakhir dipakai). Token plaintext maupun hash tidak pernah dikembalikan."
    ),
)
def list_api_tokens(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[ApiTokenResponse]]:
    tokens = api_token_service.list_tokens(db, current_user.id)
    return ApiResponse(
        data=[ApiTokenResponse.model_validate(token) for token in tokens]
    )


@router.delete(
    "/{token_id}",
    response_model=ApiResponse[MessageResponse],
    summary="Cabut personal access token",
    description=(
        "Mencabut token sehingga tidak bisa dipakai lagi untuk autentikasi. "
        "User hanya dapat mencabut token miliknya sendiri."
    ),
)
def revoke_api_token(
    token_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    token = api_token_service.get_owned_token(db, current_user.id, token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token tidak ditemukan")

    if token.revoked_at is None:
        api_token_service.revoke_token(db, token)
        log_audit(
            "REVOKE_API_TOKEN",
            user=current_user.username,
            token_id=token.id,
            token_name=token.name,
        )

    return ApiResponse(data=MessageResponse(message="Token berhasil dicabut"))
