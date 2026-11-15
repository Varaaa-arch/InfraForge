from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.database.session import get_db
from app.models.user import User
from app.services import api_token_service, auth_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau sudah kedaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolusi user dari JWT access token **atau** personal access token.

    - JWT: payload ``type=access`` + ``sub`` berisi user id.
    - PAT: hash token dicari di tabel ``api_tokens`` (aktif & belum kedaluwarsa).
    - PAT dengan scope tanpa ``write`` hanya boleh memakai method read-only.
    """
    credentials_error = _credentials_error()

    payload = decode_token(token)
    user: User | None = None
    token_scopes: list[str] | None = None
    auth_type = "jwt"

    if payload and payload.get("type") == "access":
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_error
        try:
            user = auth_service.get_user_by_id(db, int(user_id))
        except ValueError:
            raise credentials_error
    else:
        api_token = api_token_service.find_active_by_token(db, token)
        if api_token is None:
            raise credentials_error
        user = auth_service.get_user_by_id(db, api_token.user_id)
        token_scopes = api_token.scopes
        auth_type = "pat"
        if user is not None and user.is_active:
            api_token_service.touch_last_used(db, api_token)

    if user is None or not user.is_active:
        raise credentials_error

    if auth_type == "pat" and request.method not in SAFE_METHODS:
        if token_scopes is not None and "write" not in token_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token API ini hanya memiliki akses baca",
            )

    # Disimpan agar middleware audit (dan komponen lain) bisa mengetahui
    # siapa user yang sedang melakukan request.
    request.state.current_user = user
    request.state.auth_type = auth_type

    return user
