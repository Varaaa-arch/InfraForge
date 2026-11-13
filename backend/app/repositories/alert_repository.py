"""Repository untuk tabel `alert_events`."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import AlertEvent, AlertStatus


def list_events(
    db: Session,
    *,
    status: AlertStatus | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AlertEvent]:
    query = db.query(AlertEvent)
    if status is not None:
        query = query.filter(AlertEvent.status == status)
    if severity:
        query = query.filter(AlertEvent.severity == severity)
    return (
        query.order_by(AlertEvent.starts_at.desc(), AlertEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_active_by_severity(db: Session) -> dict[str, int]:
    """
    Hitung alert berstatus firing, dikelompokkan per severity.

    Catatan: alert_events tidak terikat owner (ingest dari Alertmanager),
    jadi angka ini bersifat global untuk seluruh platform.
    """
    rows = (
        db.query(AlertEvent.severity, func.count(AlertEvent.id))
        .filter(AlertEvent.status == AlertStatus.firing)
        .group_by(AlertEvent.severity)
        .all()
    )
    return {str(severity): int(count) for severity, count in rows}


def get_by_id(db: Session, event_id: int) -> AlertEvent | None:
    return db.get(AlertEvent, event_id)


def get_open_by_fingerprint(db: Session, fingerprint: str) -> AlertEvent | None:
    return (
        db.query(AlertEvent)
        .filter(
            AlertEvent.fingerprint == fingerprint,
            AlertEvent.status == AlertStatus.firing,
        )
        .order_by(AlertEvent.starts_at.desc(), AlertEvent.id.desc())
        .first()
    )


def create(
    db: Session,
    *,
    fingerprint: str,
    alert_name: str,
    status: AlertStatus,
    severity: str,
    summary: str | None,
    description: str | None,
    labels: dict[str, Any],
    annotations: dict[str, Any],
    starts_at: datetime,
    ends_at: datetime | None,
) -> AlertEvent:
    event = AlertEvent(
        fingerprint=fingerprint,
        alert_name=alert_name,
        status=status,
        severity=severity,
        summary=summary,
        description=description,
        labels=labels,
        annotations=annotations,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def resolve(db: Session, event: AlertEvent, ends_at: datetime | None) -> AlertEvent:
    event.status = AlertStatus.resolved
    event.ends_at = ends_at
    db.commit()
    db.refresh(event)
    return event
