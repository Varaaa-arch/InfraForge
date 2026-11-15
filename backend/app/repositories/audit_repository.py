"""Repository layer untuk tabel ``audit_logs``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Query, Session

from app.models.audit_log import AuditLog


def create(
    db: Session,
    *,
    action: str,
    method: str,
    path: str,
    status_code: int,
    user_id: int | None = None,
    username: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        method=method,
        path=path,
        resource_type=resource_type,
        resource_id=resource_id,
        status_code=status_code,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()
    return entry


def _apply_filters(
    query: Query[AuditLog],
    *,
    user_id: int | None = None,
    username: str | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Query[AuditLog]:
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if username is not None:
        query = query.filter(AuditLog.username == username)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    if date_from is not None:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to is not None:
        query = query.filter(AuditLog.created_at <= date_to)
    return query


def list_entries(
    db: Session,
    *,
    user_id: int | None = None,
    username: str | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLog]:
    query = _apply_filters(
        db.query(AuditLog),
        user_id=user_id,
        username=username,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )
    return (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_entries(
    db: Session,
    *,
    user_id: int | None = None,
    username: str | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> int:
    query = _apply_filters(
        db.query(AuditLog),
        user_id=user_id,
        username=username,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )
    return query.count()


def distinct_actions(db: Session) -> list[str]:
    rows = db.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    return [row[0] for row in rows]


def distinct_usernames(db: Session) -> list[str]:
    rows = (
        db.query(AuditLog.username)
        .filter(AuditLog.username.isnot(None))
        .distinct()
        .order_by(AuditLog.username)
        .all()
    )
    return [row[0] for row in rows]
