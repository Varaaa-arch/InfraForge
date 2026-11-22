"""Test pemantauan TLS/SSL: inspeksi sertifikat, cache, API, RBAC, dan alert."""

from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.roles import Permission, Role, has_permission
from app.middleware.audit_middleware import match_audit_rule
from app.models.tls_domain import TlsDomain, TlsDomainStatus
from app.models.user import User
from app.services import auth_service, tls_domain_service
from app.services.tls_domain_service import TlsInspection, TlsTargetError

PASSWORD = "password123"


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hindari DNS eksternal untuk hostname; literal IP tetap dicek asli."""
    original = tls_domain_service._resolves_to_non_public

    def fake(host: str, port: int) -> bool:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return False
        return original(host, port)

    monkeypatch.setattr(tls_domain_service, "_resolves_to_non_public", fake)


def _make_cert(
    *,
    host: str = "example.com",
    days: int = 90,
    self_signed: bool = False,
    expired: bool = False,
    san_host: str | None = None,
) -> x509.Certificate:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, host),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "InfraForge Test"),
        ]
    )
    issuer = (
        subject
        if self_signed
        else x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, "Test Intermediate CA"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test CA"),
            ]
        )
    )
    not_before = now - timedelta(days=30) if expired else now - timedelta(days=1)
    not_after = now - timedelta(days=1) if expired else now + timedelta(days=days)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(san_host or host)]),
            critical=False,
        )
    )
    if self_signed:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )
    return builder.sign(key, hashes.SHA256())


def _inspect(
    cert: x509.Certificate | None = None,
    *,
    warning_days: int = 30,
    fetch_error: BaseException | None = None,
    verified: bool = True,
    verify_error: str | None = None,
) -> TlsInspection:
    fetch = MagicMock(
        side_effect=fetch_error if fetch_error is not None else None,
        return_value=(cert or _make_cert(), "TLSv1.3"),
    )
    with (
        patch.object(tls_domain_service, "_fetch_certificate", fetch),
        patch.object(
            tls_domain_service,
            "_verify_certificate",
            return_value=(verified, verify_error),
        ),
    ):
        return tls_domain_service.inspect_target(
            "example.com", 443, warning_days, use_cache=False
        )


def _create_user(db: Session, *, role: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    username = f"tls_{suffix}"
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


def _healthy_result() -> TlsInspection:
    now = datetime.now(timezone.utc)
    return TlsInspection(
        status=TlsDomainStatus.healthy,
        checked_at=now,
        days_remaining=80,
        expiry_date=now + timedelta(days=80),
        issuer="Test CA",
        subject="example.com",
        protocol="TLSv1.3",
        trusted=True,
    )


class TestInspection:
    def test_healthy_certificate(self) -> None:
        result = _inspect(_make_cert(days=90))
        assert result.status == TlsDomainStatus.healthy
        assert result.trusted is True
        assert result.protocol == "TLSv1.3"
        assert result.days_remaining is not None and result.days_remaining >= 88

    def test_expiring_certificate(self) -> None:
        result = _inspect(_make_cert(days=5), warning_days=30)
        assert result.status == TlsDomainStatus.expiring
        assert result.trusted is True

    def test_expired_certificate(self) -> None:
        result = _inspect(_make_cert(expired=True))
        assert result.status == TlsDomainStatus.expired
        assert result.trusted is False
        assert "kedaluwarsa" in (result.error_message or "")

    def test_self_signed_certificate_is_invalid(self) -> None:
        result = _inspect(_make_cert(self_signed=True))
        assert result.status == TlsDomainStatus.invalid
        assert "self-signed" in (result.error_message or "")

    def test_hostname_mismatch_is_invalid(self) -> None:
        result = _inspect(_make_cert(san_host="other.example"))
        assert result.status == TlsDomainStatus.invalid
        assert "tidak cocok" in (result.error_message or "")

    def test_verification_failure_is_invalid(self) -> None:
        result = _inspect(verified=False, verify_error="unable to get local issuer")
        assert result.status == TlsDomainStatus.invalid
        assert "Verifikasi" in (result.error_message or "")

    def test_timeout_is_error(self) -> None:
        result = _inspect(fetch_error=TimeoutError("timeout"))
        assert result.status == TlsDomainStatus.error
        assert "timeout" in (result.error_message or "").lower()

    def test_connection_refused_is_error(self) -> None:
        result = _inspect(fetch_error=OSError("connection refused"))
        assert result.status == TlsDomainStatus.error
        assert "Tidak dapat terhubung" in (result.error_message or "")

    def test_cache_reuses_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            tls_domain_service.settings, "TLS_DOMAIN_CACHE_TTL_SECONDS", 60
        )
        tls_domain_service.clear_inspection_cache()
        fetch = MagicMock(return_value=(_make_cert(), "TLSv1.3"))
        with (
            patch.object(tls_domain_service, "_fetch_certificate", fetch),
            patch.object(
                tls_domain_service, "_verify_certificate", return_value=(True, None)
            ),
        ):
            first = tls_domain_service.inspect_target("example.com", 443, 30)
            second = tls_domain_service.inspect_target("example.com", 443, 30)
        assert first.status == second.status
        assert fetch.call_count == 1
        tls_domain_service.clear_inspection_cache()

    def test_private_ip_blocked_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            tls_domain_service.settings, "TLS_DOMAIN_ALLOW_PRIVATE_IP", False
        )
        with pytest.raises(TlsTargetError, match="privat"):
            tls_domain_service.validate_target("127.0.0.1", 443)

    def test_private_ip_allowed_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            tls_domain_service.settings, "TLS_DOMAIN_ALLOW_PRIVATE_IP", True
        )
        assert tls_domain_service.validate_target("127.0.0.1", 443) == "127.0.0.1"


class TestApi:
    def test_developer_can_create_list_check_and_delete(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role=Role.DEVELOPER.value)
        headers = _login(client, user.username)

        with patch.object(
            tls_domain_service, "inspect_target", return_value=_healthy_result()
        ):
            created = client.post(
                "/tls-domains",
                json={"name": "Public site", "host": "Example.COM", "port": 443},
                headers=headers,
            )
            assert created.status_code == 201, created.text
            data = created.json()["data"]
            assert data["host"] == "example.com"
            assert data["status"] == "healthy"
            assert data["trusted"] is True
            assert len(data["checks"]) == 1
            domain_id = data["id"]

            listed = client.get("/tls-domains", headers=headers)
            assert listed.status_code == 200, listed.text
            assert listed.json()["data"]["total"] == 1
            assert listed.json()["data"]["items"][0]["id"] == domain_id

            checked = client.post(f"/tls-domains/{domain_id}/check", headers=headers)
            assert checked.status_code == 200, checked.text
            assert len(checked.json()["data"]["checks"]) == 2

        detail = client.get(f"/tls-domains/{domain_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["data"]["checks"][0]["status"] == "healthy"

        deleted = client.delete(f"/tls-domains/{domain_id}", headers=headers)
        assert deleted.status_code == 200, deleted.text
        assert client.get(f"/tls-domains/{domain_id}", headers=headers).status_code == 404

    def test_create_without_check_is_pending(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role=Role.DEVELOPER.value)
        headers = _login(client, user.username)
        response = client.post(
            "/tls-domains",
            json={"host": "pending.example", "check_now": False},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["data"]["status"] == "pending"
        assert response.json()["data"]["checks"] == []

    def test_duplicate_target_conflict(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role=Role.DEVELOPER.value)
        headers = _login(client, user.username)
        with patch.object(
            tls_domain_service, "inspect_target", return_value=_healthy_result()
        ):
            first = client.post("/tls-domains", json={"host": "dupe.example"}, headers=headers)
            assert first.status_code == 201, first.text
        second = client.post("/tls-domains", json={"host": "DUPE.example"}, headers=headers)
        assert second.status_code == 409

    def test_viewer_cannot_mutate(self, client: TestClient, db_session: Session) -> None:
        user = _create_user(db_session, role=Role.VIEWER.value)
        headers = _login(client, user.username)
        assert client.get("/tls-domains", headers=headers).status_code == 200
        response = client.post(
            "/tls-domains", json={"host": "viewer.example"}, headers=headers
        )
        assert response.status_code == 403

    def test_update_triggers_recheck(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role=Role.DEVELOPER.value)
        headers = _login(client, user.username)
        with patch.object(
            tls_domain_service, "inspect_target", return_value=_healthy_result()
        ):
            created = client.post(
                "/tls-domains", json={"host": "old.example"}, headers=headers
            )
            assert created.status_code == 201, created.text
            domain_id = created.json()["data"]["id"]
            updated = client.patch(
                f"/tls-domains/{domain_id}",
                json={"host": "new.example", "name": "Renamed"},
                headers=headers,
            )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["host"] == "new.example"
        assert updated.json()["data"]["name"] == "Renamed"
        assert len(updated.json()["data"]["checks"]) == 2

    def test_max_targets_enforced(
        self,
        client: TestClient,
        db_session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(tls_domain_service.settings, "TLS_DOMAIN_MAX_TARGETS", 1)
        user = _create_user(db_session, role=Role.DEVELOPER.value)
        headers = _login(client, user.username)
        with patch.object(
            tls_domain_service, "inspect_target", return_value=_healthy_result()
        ):
            first = client.post(
                "/tls-domains", json={"host": "one.example"}, headers=headers
            )
            assert first.status_code == 201, first.text
        second = client.post(
            "/tls-domains", json={"host": "two.example"}, headers=headers
        )
        assert second.status_code == 409

    def test_invalid_host_rejected(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role=Role.DEVELOPER.value)
        headers = _login(client, user.username)
        response = client.post(
            "/tls-domains", json={"host": "https://example.com/path"}, headers=headers
        )
        assert response.status_code == 422


def test_rbac_matrix_and_audit_rules() -> None:
    assert has_permission(Role.DEVELOPER.value, Permission.TLS_DOMAIN_WRITE)
    assert has_permission(Role.ADMIN.value, Permission.TLS_DOMAIN_WRITE)
    assert not has_permission(Role.VIEWER.value, Permission.TLS_DOMAIN_WRITE)

    for method, path, action in (
        ("POST", "/tls-domains", "TLS_DOMAIN_CREATE"),
        ("PATCH", "/tls-domains/1", "TLS_DOMAIN_UPDATE"),
        ("DELETE", "/tls-domains/1", "TLS_DOMAIN_DELETE"),
        ("POST", "/tls-domains/1/check", "TLS_DOMAIN_CHECK"),
    ):
        matched = match_audit_rule(method, path)
        assert matched is not None
        assert matched[0].action == action


def test_alert_is_sent_and_deduplicated(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.alert import AlertChannelType
    from app.repositories import alert_channel_repository
    from app.services import alert_service

    alert_channel_repository.create(
        db_session,
        name="Ops",
        channel_type=AlertChannelType.discord,
        encrypted_discord_webhook_url="encrypted",
        encrypted_telegram_bot_token=None,
        telegram_chat_id=None,
        encrypted_slack_webhook_url=None,
        min_severity="warning",
        enabled=True,
    )
    send = MagicMock()
    monkeypatch.setattr(alert_service, "send_to_channel", send)

    user = _create_user(db_session, role=Role.DEVELOPER.value)
    headers = _login(client, user.username)
    expiring = _healthy_result()
    expiring.status = TlsDomainStatus.expiring
    expiring.days_remaining = 7

    with patch.object(
        tls_domain_service, "inspect_target", return_value=expiring
    ):
        created = client.post(
            "/tls-domains", json={"host": "alert.example"}, headers=headers
        )
        assert created.status_code == 201, created.text
        domain_id = created.json()["data"]["id"]
        assert created.json()["data"]["checks"][0]["alert_sent"] is True
        domain = db_session.get(TlsDomain, domain_id)
        assert domain is not None
        assert domain.last_alerted_at is not None

        checked = client.post(f"/tls-domains/{domain_id}/check", headers=headers)
        assert checked.status_code == 200, checked.text
        assert checked.json()["data"]["checks"][0]["alert_sent"] is False

    assert send.call_count == 1
