#!/usr/bin/env python
"""Seed deterministik untuk skenario Playwright Milestone 8.

Jalankan di dalam container backend:

    docker compose exec -T backend uv run --no-dev python scripts/seed_m8_e2e.py

Script ini membuat tiga peran (admin/developer/viewer), riwayat scan image,
target TLS, dan riwayat pemeriksaan. Data lama dengan username/host yang sama
dihapus lebih dulu agar hasil E2E stabil.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.core.roles import Role
from app.database.session import SessionLocal
from app.models.audit_log import AuditLog
from app.models.image_scan import ImageScan, ImageScanStatus
from app.models.tls_domain import TlsDomain, TlsDomainCheck, TlsDomainStatus
from app.models.user import User
from app.services import auth_service

PASSWORD = "e2e-password"
ADMIN = "e2e_m8_admin"
DEVELOPER = "e2e_m8_dev"
VIEWER = "e2e_m8_viewer"
USERNAMES = (ADMIN, DEVELOPER, VIEWER)
HOST_PREFIX = "m8-"


def _reset(db) -> None:
    db.query(AuditLog).filter(AuditLog.username.in_(USERNAMES)).delete(
        synchronize_session=False
    )
    db.query(ImageScan).filter(ImageScan.requested_by.in_(USERNAMES)).delete(
        synchronize_session=False
    )
    old_domain_ids = [
        domain_id
        for (domain_id,) in db.query(TlsDomain.id)
        .filter(TlsDomain.host.like(f"{HOST_PREFIX}%"))
        .all()
    ]
    if old_domain_ids:
        db.query(TlsDomainCheck).filter(
            TlsDomainCheck.tls_domain_id.in_(old_domain_ids)
        ).delete(synchronize_session=False)
    db.query(TlsDomain).filter(TlsDomain.host.like(f"{HOST_PREFIX}%")).delete(
        synchronize_session=False
    )
    db.query(User).filter(User.username.in_(USERNAMES)).delete(
        synchronize_session=False
    )
    db.commit()


def _findings() -> list[dict[str, object]]:
    return [
        {
            "cve_id": "CVE-2026-4242",
            "package": "openssl",
            "installed_version": "3.0.0",
            "fixed_version": "3.0.2",
            "severity": "critical",
            "title": "OpenSSL remote code execution",
            "target": "e2e/unsafe:1 (debian 12)",
            "primary_url": "https://example.test/CVE-2026-4242",
        },
        {
            "cve_id": "CVE-2026-4343",
            "package": "zlib",
            "installed_version": "1.2.13",
            "fixed_version": "1.2.14",
            "severity": "high",
            "title": "zlib denial of service",
            "target": "e2e/unsafe:1 (debian 12)",
            "primary_url": "https://example.test/CVE-2026-4343",
        },
    ]


def _scan(
    *,
    requested_by: str,
    image: str,
    status: ImageScanStatus,
    critical: int = 0,
    high: int = 0,
    medium: int = 0,
    low: int = 0,
    findings: list[dict[str, object]] | None = None,
    error_message: str | None = None,
) -> ImageScan:
    now = datetime.now(timezone.utc)
    total = critical + high + medium + low
    overall = (
        "critical"
        if critical
        else "high"
        if high
        else "medium"
        if medium
        else "low"
        if low
        else "none"
    )
    return ImageScan(
        image_name=image,
        status=status,
        overall_severity=overall,
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        low_count=low,
        total_count=total,
        findings=findings or [],
        scanner="trivy",
        error_message=error_message,
        requested_by=requested_by,
        scanned_at=now,
        image_digest="sha256:e2e0123456789",
    )


def _domain(
    *,
    name: str,
    host: str,
    status: TlsDomainStatus,
    days: int | None,
    trusted: bool,
    error_message: str | None = None,
) -> tuple[TlsDomain, TlsDomainCheck]:
    now = datetime.now(timezone.utc)
    domain = TlsDomain(
        name=name,
        host=host,
        port=443,
        enabled=True,
        warning_days=30,
        status=status,
        days_remaining=days,
        expiry_date=now + timedelta(days=days) if days is not None else None,
        issuer="InfraForge E2E CA",
        subject=host,
        protocol="TLSv1.3",
        trusted=trusted,
        error_message=error_message,
        last_checked_at=now,
        created_by=ADMIN,
    )
    check = TlsDomainCheck(
        status=status.value,
        days_remaining=days,
        expiry_date=domain.expiry_date,
        issuer=domain.issuer,
        subject=domain.subject,
        protocol=domain.protocol,
        trusted=trusted,
        error_message=error_message,
        alert_sent=False,
        checked_at=now,
    )
    return domain, check


def _trivy_available() -> bool:
    path = Path(settings.TRIVY_PATH)
    if path.is_absolute() or path.parent != Path("."):
        return path.is_file()
    return shutil.which(settings.TRIVY_PATH) is not None


def main() -> None:
    db = SessionLocal()
    try:
        _reset(db)

        users = {
            ADMIN: auth_service.create_user(
                db,
                ADMIN,
                f"{ADMIN}@example.com",
                PASSWORD,
                role=Role.ADMIN.value,
            ),
            DEVELOPER: auth_service.create_user(
                db,
                DEVELOPER,
                f"{DEVELOPER}@example.com",
                PASSWORD,
                role=Role.DEVELOPER.value,
            ),
            VIEWER: auth_service.create_user(
                db,
                VIEWER,
                f"{VIEWER}@example.com",
                PASSWORD,
                role=Role.VIEWER.value,
            ),
        }

        admin_clean = _scan(
            requested_by=ADMIN,
            image="e2e/secure:1",
            status=ImageScanStatus.completed,
        )
        admin_unsafe = _scan(
            requested_by=ADMIN,
            image="e2e/unsafe:1",
            status=ImageScanStatus.completed,
            critical=2,
            high=1,
            medium=1,
            findings=_findings(),
        )
        developer_failed = _scan(
            requested_by=DEVELOPER,
            image="e2e/missing:1",
            status=ImageScanStatus.failed,
            error_message="Trivy tidak tersedia saat seed E2E.",
        )
        viewer_scan = _scan(
            requested_by=VIEWER,
            image="e2e/viewer:1",
            status=ImageScanStatus.completed,
            critical=1,
            findings=[_findings()[0]],
        )
        db.add_all([admin_clean, admin_unsafe, developer_failed, viewer_scan])
        db.flush()

        healthy_domain, healthy_check = _domain(
            name="M8 Healthy",
            host=f"{HOST_PREFIX}healthy.example.com",
            status=TlsDomainStatus.healthy,
            days=85,
            trusted=True,
        )
        expiring_domain, expiring_check = _domain(
            name="M8 Expiring",
            host=f"{HOST_PREFIX}expiring.example.com",
            status=TlsDomainStatus.expiring,
            days=7,
            trusted=True,
        )
        expired_domain, expired_check = _domain(
            name="M8 Expired",
            host=f"{HOST_PREFIX}expired.example.com",
            status=TlsDomainStatus.expired,
            days=-2,
            trusted=False,
            error_message="Sertifikat sudah kedaluwarsa.",
        )
        invalid_domain, invalid_check = _domain(
            name="M8 Invalid",
            host=f"{HOST_PREFIX}invalid.example.com",
            status=TlsDomainStatus.invalid,
            days=40,
            trusted=False,
            error_message="Sertifikat self-signed tidak dipercaya.",
        )
        db.add_all(
            [healthy_domain, expiring_domain, expired_domain, invalid_domain]
        )
        db.flush()
        for domain, check in (
            (healthy_domain, healthy_check),
            (expiring_domain, expiring_check),
            (expired_domain, expired_check),
            (invalid_domain, invalid_check),
        ):
            check.tls_domain_id = domain.id
        db.add_all([healthy_check, expiring_check, expired_check, invalid_check])
        db.commit()

        print(
            json.dumps(
                {
                    "admin": {"username": ADMIN, "password": PASSWORD},
                    "developer": {"username": DEVELOPER, "password": PASSWORD},
                    "viewer": {"username": VIEWER, "password": PASSWORD},
                    "user_ids": {name: user.id for name, user in users.items()},
                    "image_scan_ids": {
                        "secure": admin_clean.id,
                        "unsafe": admin_unsafe.id,
                        "failed": developer_failed.id,
                        "viewer": viewer_scan.id,
                    },
                    "tls_domain_ids": {
                        "healthy": healthy_domain.id,
                        "expiring": expiring_domain.id,
                        "expired": expired_domain.id,
                        "invalid": invalid_domain.id,
                    },
                    "hosts": {
                        "healthy": healthy_domain.host,
                        "expiring": expiring_domain.host,
                        "expired": expired_domain.host,
                        "invalid": invalid_domain.host,
                    },
                    "trivy_available": _trivy_available(),
                }
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
