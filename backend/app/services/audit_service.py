"""Service penulisan audit log persisten.

Middleware ``AuditLogMiddleware`` memanggil :func:`record` setelah setiap
request yang cocok dengan daftar aturan audit. Penulisan dilakukan di session
terpisah (short-lived) agar kegagalan audit tidak pernah menggagalkan request
utama.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.audit_log import AuditLog
from app.repositories import audit_repository

# Dimatikan sementara oleh test suite agar tidak menulis ke database asli.
AUDIT_PERSIST_ENABLED: bool = True


@dataclass(frozen=True)
class AuditEvent:
    action: str
    method: str
    path: str
    status_code: int
    user_id: int | None = None
    username: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _write(db: Session, event: AuditEvent) -> AuditLog:
    return audit_repository.create(
        db,
        action=event.action,
        method=event.method,
        path=event.path,
        status_code=event.status_code,
        user_id=event.user_id,
        username=event.username,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        ip_address=event.ip_address,
        user_agent=event.user_agent,
        details=event.details or None,
    )


def record(event: AuditEvent, *, db: Session | None = None) -> AuditLog | None:
    """Simpan satu event audit.

    Args:
        event: Data event yang akan dicatat.
        db:    Session eksplisit (dipakai test). Bila ``None``, service membuka
               session sendiri dan menutupnya setelah selesai.

    Returns:
        ``AuditLog`` yang tersimpan, atau ``None`` bila persistensi dimatikan
        atau penulisan gagal (kegagalan tidak pernah dilempar ke pemanggil).
    """
    if not AUDIT_PERSIST_ENABLED:
        return None

    if db is not None:
        try:
            return _write(db, event)
        except Exception as exc:  # pragma: no cover - jalur defensif
            db.rollback()
            logger.warning(f"Gagal menulis audit log: {exc}")
            return None

    session = SessionLocal()
    try:
        return _write(session, event)
    except Exception as exc:
        session.rollback()
        logger.warning(f"Gagal menulis audit log: {exc}")
        return None
    finally:
        session.close()
