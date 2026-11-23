"""Test posture keamanan: agregasi, skor, RBAC, dan aturan audit."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.roles import Permission, Role, has_permission
from app.middleware.audit_middleware import match_audit_rule
from app.models.image_scan import ImageScan, ImageScanStatus
from app.models.tls_domain import TlsDomain, TlsDomainStatus
from app.models.user import User
from app.services import auth_service, security_posture_service

PASSWORD = "password123"


def _create_user(db: Session, *, role: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    username = f"posture_{suffix}"
    return auth_service.create_user(
        db,
        username,
        f"{username}@example.com",
        PASSWORD,
        role=role,
    )


def _login(client: TestClient, username: str) -> dict[str, str]:
    response = client.post(
        "/auth/login", data={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _secure_attrs(name: str = "web") -> dict[str, object]:
    return {
        "Name": f"/{name}",
        "State": {"Status": "running"},
        "Config": {"User": "1000", "Image": "nginx:1.27"},
        "HostConfig": {
            "Privileged": False,
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
        },
    }


def _scan(
    *,
    image: str,
    critical: int = 0,
    high: int = 0,
    status: ImageScanStatus = ImageScanStatus.completed,
    findings: list[dict[str, object]] | None = None,
) -> ImageScan:
    return ImageScan(
        image_name=image,
        status=status,
        critical_count=critical,
        high_count=high,
        medium_count=0,
        low_count=0,
        total_count=critical + high,
        findings=findings or [],
        scanned_at=datetime.now(tz=UTC),
    )


def _domain(
    *,
    host: str,
    status: TlsDomainStatus,
    error_message: str | None = None,
) -> TlsDomain:
    return TlsDomain(
        host=host,
        port=443,
        enabled=True,
        warning_days=30,
        status=status,
        error_message=error_message,
        last_checked_at=datetime.now(tz=UTC) - timedelta(hours=1),
    )


class TestScoring:
    def test_clean_posture_scores_full(self) -> None:
        result = security_posture_service._build_posture(
            [],
            [],
            [_secure_attrs()],
            None,
        )

        assert result.score == 100
        assert result.level == "aman"
        assert result.findings == []
        assert result.containers.available is True
        assert result.containers.running == 1
        assert result.containers.privileged == 0
        assert result.containers.root_user == 0
        assert all(check.status == "pass" for check in result.checks)

    def test_risky_posture_combines_all_sources(self) -> None:
        finding = {
            "cve_id": "CVE-2026-9999",
            "package": "openssl",
            "severity": "critical",
        }
        insecure = {
            "Name": "/unsafe",
            "State": {"Status": "running"},
            "Config": {"User": "root", "Image": "unsafe:latest"},
            "HostConfig": {
                "Privileged": True,
                "ReadonlyRootfs": False,
                "CapDrop": [],
                "SecurityOpt": [],
            },
        }
        result = security_posture_service._build_posture(
            [
                _scan(
                    image="unsafe:latest",
                    critical=2,
                    high=1,
                    findings=[finding],
                ),
                _scan(
                    image="broken:1",
                    status=ImageScanStatus.failed,
                ),
            ],
            [
                _domain(host="expired.example", status=TlsDomainStatus.expired),
                _domain(host="soon.example", status=TlsDomainStatus.expiring),
            ],
            [insecure],
            None,
        )

        assert result.level == "berisiko"
        assert result.score < 50
        assert result.images.critical_count == 2
        assert result.images.high_count == 1
        assert result.images.failed == 1
        assert result.tls.expired == 1
        assert result.tls.expiring == 1
        assert result.containers.privileged == 1
        assert result.containers.root_user == 1
        assert result.containers.writable_rootfs == 1
        assert result.containers.missing_cap_drop_all == 1
        assert result.containers.missing_no_new_privileges == 1
        assert result.findings
        assert result.findings[0].severity in {"critical", "high"}
        assert any(item.key == "container_privileged" and item.status == "fail" for item in result.checks)

    def test_docker_unavailable_is_reported_without_crashing(self) -> None:
        result = security_posture_service._build_posture(
            [],
            [],
            [],
            "Tidak dapat terhubung ke Docker daemon",
        )

        assert result.containers.available is False
        assert result.containers.error_message is not None
        docker_check = next(
            check for check in result.checks if check.key == "container_available"
        )
        assert docker_check.status == "unknown"


class TestApi:
    @pytest.mark.parametrize(
        "role",
        [Role.ADMIN.value, Role.DEVELOPER.value, Role.VIEWER.value],
    )
    def test_all_roles_can_read_posture(
        self,
        client: TestClient,
        db_session: Session,
        monkeypatch: pytest.MonkeyPatch,
        role: str,
    ) -> None:
        monkeypatch.setattr(
            security_posture_service,
            "_load_container_attrs",
            lambda: ([_secure_attrs()], None),
        )
        user = _create_user(db_session, role=role)
        headers = _login(client, user.username)

        response = client.get("/security/posture", headers=headers)

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["score"] == 100
        assert data["level"] == "aman"
        assert data["containers"]["available"] is True

    def test_unauthenticated_is_rejected(self, client: TestClient) -> None:
        assert client.get("/security/posture").status_code == 401

    def test_viewer_cannot_mutate_scan_or_tls(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role=Role.VIEWER.value)
        headers = _login(client, user.username)

        assert (
            client.post(
                "/image-scans", json={"image_name": "alpine:3.20"}, headers=headers
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/tls-domains", json={"host": "viewer.example"}, headers=headers
            ).status_code
            == 403
        )


def test_rbac_and_audit_rules() -> None:
    for role in (Role.ADMIN.value, Role.DEVELOPER.value, Role.VIEWER.value):
        assert has_permission(role, Permission.SECURITY_READ)
    assert not has_permission(Role.VIEWER.value, Permission.IMAGE_SCAN)
    assert not has_permission(Role.VIEWER.value, Permission.TLS_DOMAIN_WRITE)

    matched = match_audit_rule("GET", "/security/posture")
    assert matched is not None
    assert matched[0].action == "SECURITY_POSTURE_READ"
    assert matched[0].resource_type == "security_posture"
