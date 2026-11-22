"""Test pemindaian kerentanan image: parser, API, RBAC, dan alert threshold."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.core.roles import Role
from app.middleware.audit_middleware import match_audit_rule
from app.models.alert import AlertChannelType
from app.models.image_scan import ImageScan, ImageScanStatus
from app.models.user import User
from app.services import auth_service, image_scan_service
from app.services.image_scan_service import ScanError, TrivySummary

PASSWORD = "password123"


def _create_user(db: Session, *, role: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    username = f"imgscan_{suffix}"
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


def _create_project(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/projects",
        json={"name": f"scan-{uuid.uuid4().hex[:6]}", "description": "scan"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return int(response.json()["data"]["id"])


def _finding(
    cve_id: str = "CVE-2026-0001",
    severity: str = "critical",
) -> dict[str, object]:
    return {
        "cve_id": cve_id,
        "package": "openssl",
        "installed_version": "3.0.0",
        "fixed_version": "3.0.1",
        "severity": severity,
        "title": "Contoh kerentanan",
        "target": "debian 12",
        "primary_url": "https://avd.aquasec.com/nvd/cve-2026-0001",
    }


def _summary(
    *,
    critical: int = 1,
    high: int = 2,
    medium: int = 3,
    low: int = 4,
    findings: list[dict[str, object]] | None = None,
) -> TrivySummary:
    return TrivySummary(
        image_digest="sha256:0123456789abcdef",
        overall_severity="critical" if critical else "high",
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        low_count=low,
        total_count=critical + high + medium + low,
        findings=findings if findings is not None else [_finding()],
    )


def _trivy_payload() -> dict[str, object]:
    return {
        "ArtifactName": "nginx:1.27",
        "Metadata": {"ImageID": "sha256:abcdef", "RepoDigests": []},
        "Results": [
            {
                "Target": "nginx:1.27 (debian 12)",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-1111",
                        "PkgName": "openssl",
                        "InstalledVersion": "3.0.0",
                        "FixedVersion": "3.0.1",
                        "Severity": "CRITICAL",
                        "Title": "OpenSSL issue",
                        "PrimaryURL": "https://example.test/cve",
                    },
                    {
                        "VulnerabilityID": "CVE-2026-2222",
                        "PkgName": "zlib",
                        "Severity": "HIGH",
                    },
                    {
                        "VulnerabilityID": "CVE-2026-3333",
                        "PkgName": "curl",
                        "Severity": "MEDIUM",
                    },
                    {
                        "VulnerabilityID": "CVE-2026-4444",
                        "PkgName": "bash",
                        "Severity": "LOW",
                    },
                    {
                        "VulnerabilityID": "CVE-2026-5555",
                        "PkgName": "custom",
                        "Severity": "UNKNOWN",
                    },
                ],
            }
        ],
    }


class TestParser:
    def test_parses_counts_digest_and_findings(self) -> None:
        summary = image_scan_service.parse_trivy_output(
            json.dumps(_trivy_payload()), max_findings=10
        )
        assert summary.image_digest == "sha256:abcdef"
        assert summary.critical_count == 1
        assert summary.high_count == 1
        assert summary.medium_count == 1
        assert summary.low_count == 1
        assert summary.total_count == 5
        assert summary.overall_severity == "critical"
        assert summary.findings[0]["cve_id"] == "CVE-2026-1111"
        assert summary.findings[0]["severity"] == "critical"
        assert summary.findings[-1]["severity"] == "unknown"

    def test_limits_saved_findings(self) -> None:
        summary = image_scan_service.parse_trivy_output(
            json.dumps(_trivy_payload()), max_findings=2
        )
        assert summary.total_count == 5
        assert len(summary.findings) == 2

    def test_empty_results_is_clean(self) -> None:
        summary = image_scan_service.parse_trivy_output('{"Results": []}')
        assert summary.total_count == 0
        assert summary.overall_severity == "none"
        assert summary.findings == []

    def test_invalid_json_raises_scan_error(self) -> None:
        with pytest.raises(ScanError, match="JSON"):
            image_scan_service.parse_trivy_output("bukan-json")


class TestScanApi:
    def test_developer_triggers_scan_and_gets_detail(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role=Role.DEVELOPER.value)
        headers = _login(client, user.username)
        project_id = _create_project(client, headers)

        with patch(
            "app.services.image_scan_service._scan_sync",
            return_value=_summary(),
        ):
            response = client.post(
                "/image-scans",
                json={"image_name": "nginx:1.27", "project_id": project_id},
                headers=headers,
            )

        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["image_name"] == "nginx:1.27"
        assert data["status"] == "completed"
        assert data["project_id"] == project_id
        assert data["requested_by"] == user.username
        assert data["critical_count"] == 1
        assert data["high_count"] == 2
        assert data["total_count"] == 10
        assert data["image_digest"] == "sha256:0123456789abcdef"
        assert data["findings"][0]["cve_id"] == "CVE-2026-0001"
        assert data["scanned_at"] is not None

    def test_viewer_cannot_trigger_but_can_list(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role=Role.VIEWER.value)
        headers = _login(client, user.username)

        denied = client.post(
            "/image-scans", json={"image_name": "nginx:1.27"}, headers=headers
        )
        assert denied.status_code == 403

        listed = client.get("/image-scans", headers=headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()["data"]["items"] == []

    def test_missing_trivy_marks_scan_failed(
        self,
        client: TestClient,
        db_session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = _create_user(db_session, role=Role.DEVELOPER.value)
        headers = _login(client, user.username)
        monkeypatch.setattr(settings, "TRIVY_PATH", "/nonexistent/trivy-binary")

        response = client.post(
            "/image-scans",
            json={"image_name": "alpine:3.20"},
            headers=headers,
        )

        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["status"] == "failed"
        assert "Trivy tidak tersedia" in data["error_message"]
        assert data["scanned_at"] is not None

    def test_scan_list_and_detail_are_scoped_to_owner(
        self, client: TestClient, db_session: Session
    ) -> None:
        owner = _create_user(db_session, role=Role.DEVELOPER.value)
        other = _create_user(db_session, role=Role.DEVELOPER.value)
        admin = _create_user(db_session, role=Role.ADMIN.value)
        owner_headers = _login(client, owner.username)
        other_headers = _login(client, other.username)
        admin_headers = _login(client, admin.username)

        with patch(
            "app.services.image_scan_service._scan_sync",
            return_value=_summary(findings=[_finding("CVE-OWNER")]),
        ):
            created = client.post(
                "/image-scans",
                json={"image_name": "owner/app:1"},
                headers=owner_headers,
            )
        assert created.status_code == 201, created.text
        scan_id = created.json()["data"]["id"]

        owner_list = client.get("/image-scans", headers=owner_headers)
        assert owner_list.status_code == 200
        assert owner_list.json()["data"]["total"] == 1

        other_list = client.get("/image-scans", headers=other_headers)
        assert other_list.status_code == 200
        assert other_list.json()["data"]["total"] == 0
        denied = client.get(f"/image-scans/{scan_id}", headers=other_headers)
        assert denied.status_code == 404

        admin_list = client.get("/image-scans", headers=admin_headers)
        assert admin_list.status_code == 200
        assert admin_list.json()["data"]["total"] == 1
        admin_detail = client.get(f"/image-scans/{scan_id}", headers=admin_headers)
        assert admin_detail.status_code == 200
        assert admin_detail.json()["data"]["findings"][0]["cve_id"] == "CVE-OWNER"

    def test_project_must_belong_to_user(
        self, client: TestClient, db_session: Session
    ) -> None:
        owner = _create_user(db_session, role=Role.DEVELOPER.value)
        other = _create_user(db_session, role=Role.DEVELOPER.value)
        owner_headers = _login(client, owner.username)
        other_headers = _login(client, other.username)
        project_id = _create_project(client, owner_headers)

        response = client.post(
            "/image-scans",
            json={"image_name": "nginx:1.27", "project_id": project_id},
            headers=other_headers,
        )
        assert response.status_code == 404

    def test_rescan_creates_new_history_row(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role=Role.DEVELOPER.value)
        headers = _login(client, user.username)
        project_id = _create_project(client, headers)

        with patch(
            "app.services.image_scan_service._scan_sync",
            return_value=_summary(critical=0, high=1),
        ):
            first = client.post(
                "/image-scans",
                json={"image_name": "redis:7", "project_id": project_id},
                headers=headers,
            )
            assert first.status_code == 201, first.text
            second = client.post(
                f"/image-scans/{first.json()['data']['id']}/rescan",
                headers=headers,
            )

        assert second.status_code == 201, second.text
        data = second.json()["data"]
        assert data["id"] != first.json()["data"]["id"]
        assert data["image_name"] == "redis:7"
        assert data["project_id"] == project_id

        listed = client.get("/image-scans", headers=headers)
        assert listed.json()["data"]["total"] == 2

    def test_image_filter_and_pagination(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role=Role.DEVELOPER.value)
        headers = _login(client, user.username)

        with patch(
            "app.services.image_scan_service._scan_sync",
            return_value=_summary(),
        ):
            for image in ("nginx:1.27", "redis:7", "nginx:1.28"):
                response = client.post(
                    "/image-scans", json={"image_name": image}, headers=headers
                )
                assert response.status_code == 201, response.text

        filtered = client.get("/image-scans?image=nginx&limit=1", headers=headers)
        assert filtered.status_code == 200
        data = filtered.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 1
        assert data["limit"] == 1


class TestNotificationsAndAudit:
    def test_threshold_sends_notification(
        self, db_session: Session
    ) -> None:
        scan = ImageScan(
            image_name="nginx:1.27",
            status=ImageScanStatus.completed,
            overall_severity="critical",
            critical_count=2,
            high_count=5,
            total_count=7,
            findings=[],
        )
        db_session.add(scan)
        db_session.flush()
        channel = MagicMock()
        channel.name = "Ops"

        with patch(
            "app.repositories.alert_channel_repository.list_enabled_for_severity",
            return_value=[channel],
        ), patch("app.services.alert_service.send_to_channel") as send:
            image_scan_service.notify_vulnerability_threshold(db_session, scan)

        send.assert_called_once()
        event = send.call_args.args[1]
        assert event.alert_name == "ImageVulnerabilitiesDetected"
        assert event.severity == "critical"
        assert event.labels["image"] == "nginx:1.27"

    def test_no_notification_without_findings(self, db_session: Session) -> None:
        scan = ImageScan(
            image_name="nginx:1.27",
            status=ImageScanStatus.completed,
            overall_severity="none",
            critical_count=0,
            high_count=0,
            total_count=0,
            findings=[],
        )
        db_session.add(scan)
        db_session.flush()

        with patch(
            "app.repositories.alert_channel_repository.list_enabled_for_severity",
            return_value=[MagicMock()],
        ), patch("app.services.alert_service.send_to_channel") as send:
            image_scan_service.notify_vulnerability_threshold(db_session, scan)

        send.assert_not_called()

    def test_audit_rules(self) -> None:
        assert match_audit_rule("POST", "/image-scans") is not None
        matched = match_audit_rule("POST", "/image-scans/42/rescan")
        assert matched is not None
        assert matched[0].action == "IMAGE_SCAN_RESCAN"
        assert matched[1] == {"id": "42"}

    def test_alert_channel_enum_still_importable(self) -> None:
        assert AlertChannelType.discord.value == "discord"
