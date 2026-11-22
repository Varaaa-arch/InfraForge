"""Repository untuk target TLS/SSL dan riwayat pemeriksaan sertifikat."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.tls_domain import TlsDomain, TlsDomainCheck, TlsDomainStatus


def list_domains(
    db: Session,
    *,
    search: str | None = None,
    status: TlsDomainStatus | None = None,
    enabled: bool | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[TlsDomain], int]:
    query = db.query(TlsDomain)
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(
            or_(TlsDomain.host.ilike(needle), TlsDomain.name.ilike(needle))
        )
    if status is not None:
        query = query.filter(TlsDomain.status == status)
    if enabled is not None:
        query = query.filter(TlsDomain.enabled.is_(enabled))
    total = query.with_entities(func.count(TlsDomain.id)).scalar() or 0
    domains = (
        query.order_by(TlsDomain.host.asc(), TlsDomain.port.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return domains, total


def get_by_id(db: Session, domain_id: int) -> TlsDomain | None:
    return db.get(TlsDomain, domain_id)


def get_by_host_port(db: Session, host: str, port: int) -> TlsDomain | None:
    return (
        db.query(TlsDomain)
        .filter(TlsDomain.host == host, TlsDomain.port == port)
        .first()
    )


def count_domains(db: Session) -> int:
    return db.query(func.count(TlsDomain.id)).scalar() or 0


def create(
    db: Session,
    *,
    name: str | None,
    host: str,
    port: int,
    enabled: bool,
    warning_days: int,
    created_by: str | None,
) -> TlsDomain:
    domain = TlsDomain(
        name=name,
        host=host,
        port=port,
        enabled=enabled,
        warning_days=warning_days,
        created_by=created_by,
    )
    db.add(domain)
    db.commit()
    db.refresh(domain)
    return domain


def save(db: Session, domain: TlsDomain) -> TlsDomain:
    db.commit()
    db.refresh(domain)
    return domain


def delete(db: Session, domain: TlsDomain) -> None:
    db.delete(domain)
    db.commit()


def create_check(
    db: Session,
    *,
    tls_domain_id: int,
    status: str,
    days_remaining: int | None,
    expiry_date: datetime | None,
    issuer: str | None,
    subject: str | None,
    protocol: str | None,
    trusted: bool,
    error_message: str | None,
    alert_sent: bool,
    checked_at: datetime,
) -> TlsDomainCheck:
    check = TlsDomainCheck(
        tls_domain_id=tls_domain_id,
        status=status,
        days_remaining=days_remaining,
        expiry_date=expiry_date,
        issuer=issuer,
        subject=subject,
        protocol=protocol,
        trusted=trusted,
        error_message=error_message,
        alert_sent=alert_sent,
        checked_at=checked_at,
    )
    db.add(check)
    db.commit()
    db.refresh(check)
    return check


def list_checks(
    db: Session, domain_id: int, *, limit: int = 20
) -> list[TlsDomainCheck]:
    return (
        db.query(TlsDomainCheck)
        .filter(TlsDomainCheck.tls_domain_id == domain_id)
        .order_by(TlsDomainCheck.checked_at.desc(), TlsDomainCheck.id.desc())
        .limit(limit)
        .all()
    )
