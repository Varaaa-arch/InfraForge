"""Service Personal Access Token (PAT).

Format token: ``if_<prefix>_<secret>``.
- ``prefix`` (8 hex char) disimpan untuk ditampilkan di UI.
- Hanya **hash SHA-256** dari token lengkap yang disimpan di database.
- Token plaintext hanya dikembalikan sekali saat dibuat.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.api_token import ApiToken

TOKEN_PREFIX = "if_"
LAST_USED_THROTTLE = timedelta(seconds=60)
VALID_SCOPES = frozenset({"read", "write"})


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(
    db: Session,
    *,
    user_id: int,
    name: str,
    scopes: list[str] | None = None,
    expires_in_days: int | None = None,
) -> tuple[ApiToken, str]:
    """Buat token baru dan kembalikan ``(record, token_plaintext)``."""
    token_prefix = secrets.token_hex(4)
    secret = secrets.token_hex(32)
    token = f"{TOKEN_PREFIX}{token_prefix}_{secret}"

    expires_at = (
        _now() + timedelta(days=expires_in_days) if expires_in_days is not None else None
    )

    record = ApiToken(
        user_id=user_id,
        name=name,
        token_hash=hash_token(token),
        prefix=f"{TOKEN_PREFIX}{token_prefix}",
        scopes=list(scopes) if scopes is not None else None,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, token


def list_tokens(db: Session, user_id: int) -> list[ApiToken]:
    return (
        db.query(ApiToken)
        .filter(ApiToken.user_id == user_id)
        .order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
        .all()
    )


def get_owned_token(db: Session, user_id: int, token_id: int) -> ApiToken | None:
    return (
        db.query(ApiToken)
        .filter(ApiToken.id == token_id, ApiToken.user_id == user_id)
        .first()
    )


def revoke_token(db: Session, token: ApiToken) -> ApiToken:
    token.revoked_at = _now()
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def find_active_by_token(db: Session, token: str) -> ApiToken | None:
    """Cari token aktif (belum dicabut & belum kedaluwarsa) berdasarkan hash."""
    record = (
        db.query(ApiToken)
        .filter(ApiToken.token_hash == hash_token(token))
        .first()
    )
    if record is None:
        return None
    if record.revoked_at is not None:
        return None
    now = _now()
    if record.expires_at is not None and record.expires_at <= now:
        return None
    return record


def touch_last_used(db: Session, token: ApiToken) -> None:
    """Perbarui ``last_used_at`` (dibatasi sekali per menit agar hemat write)."""
    now = _now()
    if token.last_used_at is not None:
        last_used = token.last_used_at
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)
        if now - last_used < LAST_USED_THROTTLE:
            return

    token.last_used_at = now
    db.add(token)
    db.commit()
