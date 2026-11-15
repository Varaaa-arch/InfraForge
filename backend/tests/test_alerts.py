"""Test untuk Alerting: ingest webhook, formatting, channel, dan metrics."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.alert import AlertChannelType, AlertEvent, AlertStatus
from app.schemas.alert import AlertChannelCreate, AlertmanagerPayload
from app.services import alert_channel_service, alert_service, metrics_service


def _unique_user() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"alert_{suffix}",
        "email": f"alert_{suffix}@example.com",
        "password": "password123",
    }


def _register_and_login(client: TestClient, payload: dict[str, str]) -> dict[str, str]:
    client.post("/auth/register", json=payload)
    response = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    return dict(response.json()["data"])


def _auth_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _payload(
    *,
    status: str = "firing",
    fingerprint: str = "abc123",
    severity: str = "critical",
    alert_name: str = "HighHostCPUUsage",
    starts_at: str = "2026-11-12T00:00:00Z",
    ends_at: str | None = None,
) -> dict:
    return {
        "version": "4",
        "status": status,
        "receiver": "infraforge-webhook",
        "groupKey": "{}:{}",
        "alerts": [
            {
                "status": status,
                "labels": {
                    "alertname": alert_name,
                    "severity": severity,
                    "container": "infraforge-backend",
                    "instance": "host",
                },
                "annotations": {
                    "summary": "CPU tinggi",
                    "description": "CPU > 90% selama 5 menit.",
                },
                "startsAt": starts_at,
                "endsAt": ends_at,
                "generatorURL": "http://prometheus/graph",
                "fingerprint": fingerprint,
            }
        ],
    }


def _channel_payload(
    *,
    name: str = "Discord DevOps",
    channel_type: str = "discord",
    url: str = "https://discord.com/api/webhooks/123/token",
    min_severity: str = "info",
) -> dict:
    if channel_type == "telegram":
        return {
            "name": name,
            "type": "telegram",
            "telegram_bot_token": "123456:bot-token",
            "telegram_chat_id": "-100123",
            "min_severity": min_severity,
            "enabled": True,
        }
    if channel_type == "slack":
        return {
            "name": name,
            "type": "slack",
            "slack_webhook_url": url,
            "min_severity": min_severity,
            "enabled": True,
        }
    return {
        "name": name,
        "type": "discord",
        "discord_webhook_url": url,
        "min_severity": min_severity,
        "enabled": True,
    }


class TestFormatting:
    def test_discord_payload_firing(self) -> None:
        event = alert_service.NotificationEvent(
            alert_name="HighHostCPUUsage",
            status="firing",
            severity="critical",
            summary="CPU tinggi",
            description="CPU > 90%",
            labels={"container": "infraforge-backend", "instance": "host"},
            annotations={},
            starts_at=datetime(2026, 11, 12, tzinfo=timezone.utc),
            ends_at=None,
        )
        payload = alert_service.build_discord_payload(event)
        embed = payload["embeds"][0]
        assert embed["title"] == "[FIRING] HighHostCPUUsage"
        assert embed["color"] == 0xEF4444
        field_names = [field["name"] for field in embed["fields"]]
        assert "Container" in field_names
        assert "Instance" in field_names

    def test_discord_payload_resolved_is_green(self) -> None:
        event = alert_service.NotificationEvent(
            alert_name="HighHostCPUUsage",
            status="resolved",
            severity="critical",
            summary=None,
            description=None,
            labels={},
            annotations={},
            starts_at=datetime(2026, 11, 12, tzinfo=timezone.utc),
            ends_at=datetime(2026, 11, 12, 1, tzinfo=timezone.utc),
        )
        payload = alert_service.build_discord_payload(event)
        assert payload["embeds"][0]["color"] == 0x22C55E
        assert payload["embeds"][0]["title"] == "[RESOLVED] HighHostCPUUsage"

    def test_telegram_message_escapes_html(self) -> None:
        event = alert_service.NotificationEvent(
            alert_name="<script>alert(1)</script>",
            status="firing",
            severity="critical",
            summary="x",
            description='<b>boom</b> & "quoted"',
            labels={"container": "infraforge-backend"},
            annotations={},
            starts_at=datetime(2026, 11, 12, tzinfo=timezone.utc),
            ends_at=None,
        )
        message = alert_service.build_telegram_message(event)
        assert "<script>" not in message
        assert "&lt;script&gt;" in message
        assert "&lt;b&gt;boom&lt;/b&gt;" in message

    def test_slack_payload_firing(self) -> None:
        event = alert_service.NotificationEvent(
            alert_name="HighHostCPUUsage",
            status="firing",
            severity="critical",
            summary="CPU tinggi",
            description="CPU > 90%",
            labels={"container": "infraforge-backend", "instance": "host"},
            annotations={},
            starts_at=datetime(2026, 11, 12, tzinfo=timezone.utc),
            ends_at=None,
        )
        payload = alert_service.build_slack_payload(event)
        attachment = payload["attachments"][0]
        assert attachment["color"] == "#EF4444"
        assert payload["text"] == "[FIRING] HighHostCPUUsage — critical"
        blocks = attachment["blocks"]
        assert blocks[0]["text"]["text"] == "[FIRING] HighHostCPUUsage"
        rendered = str(payload)
        assert "Severity" in rendered
        assert "Container" in rendered
        assert "CPU &gt; 90%" in rendered

    def test_slack_payload_resolved_is_green(self) -> None:
        event = alert_service.NotificationEvent(
            alert_name="HighHostCPUUsage",
            status="resolved",
            severity="warning",
            summary=None,
            description=None,
            labels={},
            annotations={},
            starts_at=datetime(2026, 11, 12, tzinfo=timezone.utc),
            ends_at=datetime(2026, 11, 12, 1, tzinfo=timezone.utc),
        )
        payload = alert_service.build_slack_payload(event)
        assert payload["attachments"][0]["color"] == "#22C55E"
        assert payload["text"] == "[RESOLVED] HighHostCPUUsage — warning"


class TestIngest:
    def test_firing_creates_event(self, db_session: Session) -> None:
        result = alert_service.ingest(
            db_session, AlertmanagerPayload(**_payload())
        )
        assert result.received == 1
        assert result.created == 1
        assert result.resolved == 0
        assert len(result.event_ids) == 1
        event = db_session.get(AlertEvent, result.event_ids[0])
        assert event is not None
        assert event.status == AlertStatus.firing
        assert event.severity == "critical"
        assert event.summary == "CPU tinggi"

    def test_duplicate_firing_is_ignored(self, db_session: Session) -> None:
        alert_service.ingest(db_session, AlertmanagerPayload(**_payload()))
        second = alert_service.ingest(
            db_session, AlertmanagerPayload(**_payload())
        )
        assert second.created == 0
        assert second.event_ids == []
        assert db_session.query(AlertEvent).count() == 1

    def test_resolved_updates_open_event(self, db_session: Session) -> None:
        first = alert_service.ingest(
            db_session, AlertmanagerPayload(**_payload())
        )
        result = alert_service.ingest(
            db_session,
            AlertmanagerPayload(
                **_payload(
                    status="resolved",
                    ends_at="2026-11-12T00:10:00Z",
                )
            ),
        )
        assert result.resolved == 1
        event = db_session.get(AlertEvent, first.event_ids[0])
        assert event is not None
        assert event.status == AlertStatus.resolved
        assert event.ends_at is not None

    def test_refiring_after_resolve_creates_new_row(
        self, db_session: Session
    ) -> None:
        alert_service.ingest(db_session, AlertmanagerPayload(**_payload()))
        alert_service.ingest(
            db_session,
            AlertmanagerPayload(**_payload(status="resolved")),
        )
        third = alert_service.ingest(
            db_session, AlertmanagerPayload(**_payload())
        )
        assert third.created == 1
        assert db_session.query(AlertEvent).count() == 2

    def test_resolved_without_firing_is_ignored(self, db_session: Session) -> None:
        result = alert_service.ingest(
            db_session,
            AlertmanagerPayload(**_payload(status="resolved")),
        )
        assert result.resolved == 0
        assert db_session.query(AlertEvent).count() == 0


class TestChannelService:
    def test_create_discord_encrypts_url(self, db_session: Session) -> None:
        channel = alert_channel_service.create_channel(
            db_session,
            AlertChannelCreate(**_channel_payload()),
        )
        assert channel.channel_type == AlertChannelType.discord
        assert channel.encrypted_discord_webhook_url != (
            "https://discord.com/api/webhooks/123/token"
        )
        assert alert_channel_service.decrypt_discord_webhook_url(channel) == (
            "https://discord.com/api/webhooks/123/token"
        )

    def test_create_telegram(self, db_session: Session) -> None:
        channel = alert_channel_service.create_channel(
            db_session,
            AlertChannelCreate(
                **_channel_payload(channel_type="telegram")
            ),
        )
        assert channel.channel_type == AlertChannelType.telegram
        assert channel.telegram_chat_id == "-100123"
        assert alert_channel_service.decrypt_telegram_bot_token(channel) == (
            "123456:bot-token"
        )

    def test_update_name_only_keeps_valid_config(self, db_session: Session) -> None:
        from app.schemas.alert import AlertChannelUpdate

        channel = alert_channel_service.create_channel(
            db_session,
            AlertChannelCreate(**_channel_payload()),
        )
        updated = alert_channel_service.update_channel(
            db_session,
            channel,
            AlertChannelUpdate(name="Discord Baru", enabled=False),
        )
        assert updated.name == "Discord Baru"
        assert updated.enabled is False
        assert alert_channel_service.decrypt_discord_webhook_url(updated) == (
            "https://discord.com/api/webhooks/123/token"
        )

    def test_response_hides_secrets(self, db_session: Session) -> None:
        channel = alert_channel_service.create_channel(
            db_session,
            AlertChannelCreate(**_channel_payload()),
        )
        response = alert_channel_service.to_response(channel)
        assert response.has_discord_webhook is True
        assert response.has_telegram_bot_token is False
        assert "discord.com" not in response.model_dump_json()

    def test_discord_requires_webhook_url(self) -> None:
        with pytest.raises(ValidationError):
            AlertChannelCreate(name="x", type="discord")

    def test_telegram_requires_chat_id(self) -> None:
        with pytest.raises(ValidationError):
            AlertChannelCreate(
                name="x",
                type="telegram",
                telegram_bot_token="token",
            )

    def test_create_slack_encrypts_url(self, db_session: Session) -> None:
        url = "https://hooks.slack.com/services/T000/B000/secret"
        channel = alert_channel_service.create_channel(
            db_session,
            AlertChannelCreate(**_channel_payload(channel_type="slack", url=url)),
        )
        assert channel.channel_type == AlertChannelType.slack
        assert channel.encrypted_slack_webhook_url != url
        assert alert_channel_service.decrypt_slack_webhook_url(channel) == url
        assert channel.min_severity == "info"

        response = alert_channel_service.to_response(channel)
        assert response.has_slack_webhook is True
        assert response.has_discord_webhook is False
        assert "hooks.slack.com" not in response.model_dump_json()

    def test_slack_requires_webhook_url(self) -> None:
        with pytest.raises(ValidationError):
            AlertChannelCreate(name="x", type="slack")

    def test_min_severity_is_stored_and_validated(self, db_session: Session) -> None:
        channel = alert_channel_service.create_channel(
            db_session,
            AlertChannelCreate(
                **_channel_payload(min_severity="warning"),
            ),
        )
        assert channel.min_severity == "warning"

        with pytest.raises(ValidationError):
            AlertChannelCreate(**_channel_payload(min_severity="debug"))

    def test_update_slack_url_and_min_severity(self, db_session: Session) -> None:
        from app.schemas.alert import AlertChannelUpdate

        channel = alert_channel_service.create_channel(
            db_session,
            AlertChannelCreate(**_channel_payload(channel_type="slack")),
        )
        new_url = "https://hooks.slack.com/services/T111/B222/new"
        updated = alert_channel_service.update_channel(
            db_session,
            channel,
            AlertChannelUpdate(slack_webhook_url=new_url, min_severity="critical"),
        )
        assert updated.min_severity == "critical"
        assert alert_channel_service.decrypt_slack_webhook_url(updated) == new_url


class TestSeverityRouting:
    def _create(
        self,
        db: Session,
        *,
        name: str,
        min_severity: str,
        enabled: bool = True,
    ) -> int:
        channel = alert_channel_service.create_channel(
            db,
            AlertChannelCreate(
                **_channel_payload(
                    name=name,
                    channel_type="slack",
                    min_severity=min_severity,
                ),
            ),
        )
        if not enabled:
            channel.enabled = False
            db.commit()
        return channel.id

    def test_enabled_channels_filtered_by_severity(self, db_session: Session) -> None:
        from app.repositories import alert_channel_repository

        info_id = self._create(db_session, name="Info", min_severity="info")
        warning_id = self._create(db_session, name="Warning", min_severity="warning")
        critical_id = self._create(
            db_session, name="Critical", min_severity="critical"
        )
        self._create(
            db_session, name="Disabled", min_severity="info", enabled=False
        )

        def ids(severity: str | None) -> set[int]:
            return {
                channel.id
                for channel in alert_channel_repository.list_enabled_for_severity(
                    db_session, severity
                )
            }

        assert ids("info") == {info_id}
        assert ids("warning") == {info_id, warning_id}
        assert ids("critical") == {info_id, warning_id, critical_id}
        assert ids("unknown") == {info_id}
        assert ids(None) == {info_id}

    def test_unknown_severity_treated_as_info(self) -> None:
        from app.models.alert import severity_rank

        assert severity_rank("unknown") == severity_rank("info")
        assert severity_rank(None) == 0
        assert severity_rank("CRITICAL") == severity_rank("critical")


class TestAlertsAPI:
    def test_list_requires_auth(self, client: TestClient) -> None:
        assert client.get("/alerts").status_code == 401
        assert client.get("/alert-channels").status_code == 401

    def test_create_list_and_delete_channel(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())

        created = client.post(
            "/alert-channels",
            headers=_auth_header(tokens),
            json=_channel_payload(),
        )
        assert created.status_code == 201
        body = created.json()["data"]
        assert body["has_discord_webhook"] is True
        assert "discord_webhook_url" not in body

        listed = client.get("/alert-channels", headers=_auth_header(tokens))
        assert listed.status_code == 200
        assert len(listed.json()["data"]) >= 1

        deleted = client.delete(
            f"/alert-channels/{body['id']}", headers=_auth_header(tokens)
        )
        assert deleted.status_code == 200

    def test_update_channel(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        created = client.post(
            "/alert-channels",
            headers=_auth_header(tokens),
            json=_channel_payload(),
        ).json()["data"]

        updated = client.patch(
            f"/alert-channels/{created['id']}",
            headers=_auth_header(tokens),
            json={"enabled": False, "name": "Dimatikan"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["enabled"] is False
        assert updated.json()["data"]["name"] == "Dimatikan"

    def test_webhook_requires_configuration(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", "")
        response = client.post("/alerts/webhook?token=x", json=_payload())
        assert response.status_code == 503

    def test_webhook_rejects_invalid_token(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", "secret")
        response = client.post("/alerts/webhook?token=wrong", json=_payload())
        assert response.status_code == 401

    def test_webhook_ingests_and_lists_alert(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        monkeypatch.setattr(settings, "ALERT_WEBHOOK_SECRET", "secret")
        dispatched: list[list[int]] = []
        monkeypatch.setattr(
            alert_service,
            "dispatch_event_notifications",
            lambda event_ids: dispatched.append(event_ids),
        )

        response = client.post("/alerts/webhook?token=secret", json=_payload())
        assert response.status_code == 202
        assert response.json()["data"]["created"] == 1
        assert dispatched and dispatched[0]

        listed = client.get("/alerts", headers=_auth_header(tokens))
        assert listed.status_code == 200
        events = listed.json()["data"]
        assert len(events) == 1
        assert events[0]["alert_name"] == "HighHostCPUUsage"
        assert events[0]["status"] == "firing"

        filtered = client.get(
            "/alerts?status=firing&severity=critical",
            headers=_auth_header(tokens),
        )
        assert len(filtered.json()["data"]) == 1

        empty = client.get(
            "/alerts?severity=warning",
            headers=_auth_header(tokens),
        )
        assert empty.json()["data"] == []

    def test_create_slack_channel_with_min_severity(
        self, client: TestClient
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        created = client.post(
            "/alert-channels",
            headers=_auth_header(tokens),
            json=_channel_payload(
                channel_type="slack",
                url="https://hooks.slack.com/services/T000/B000/secret",
                min_severity="critical",
            ),
        )
        assert created.status_code == 201
        body = created.json()["data"]
        assert body["type"] == "slack"
        assert body["has_slack_webhook"] is True
        assert body["min_severity"] == "critical"
        assert "slack_webhook_url" not in body
        assert "hooks.slack.com" not in created.text

    def test_create_channel_rejects_invalid_severity(
        self, client: TestClient
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        response = client.post(
            "/alert-channels",
            headers=_auth_header(tokens),
            json=_channel_payload(min_severity="debug"),
        )
        assert response.status_code == 422

    def test_test_channel_uses_channel_threshold(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        created = client.post(
            "/alert-channels",
            headers=_auth_header(tokens),
            json=_channel_payload(
                channel_type="slack",
                min_severity="warning",
            ),
        ).json()["data"]

        sent: list[dict[str, object]] = []
        monkeypatch.setattr(
            alert_service,
            "_send_slack",
            lambda url, payload: sent.append(payload),
        )
        response = client.post(
            f"/alert-channels/{created['id']}/test",
            headers=_auth_header(tokens),
        )
        assert response.status_code == 200
        assert sent
        assert "*Severity:*\\nwarning" in str(sent[0])

    def test_test_channel_severity_override(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        created = client.post(
            "/alert-channels",
            headers=_auth_header(tokens),
            json=_channel_payload(channel_type="slack"),
        ).json()["data"]

        sent: list[dict[str, object]] = []
        monkeypatch.setattr(
            alert_service,
            "_send_slack",
            lambda url, payload: sent.append(payload),
        )
        response = client.post(
            f"/alert-channels/{created['id']}/test",
            headers=_auth_header(tokens),
            json={"severity": "critical"},
        )
        assert response.status_code == 200
        assert "*Severity:*\\ncritical" in str(sent[0])

    def test_test_channel_failure_returns_502(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        created = client.post(
            "/alert-channels",
            headers=_auth_header(tokens),
            json=_channel_payload(),
        ).json()["data"]

        def _fail(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(alert_service, "_send_discord", _fail)
        response = client.post(
            f"/alert-channels/{created['id']}/test",
            headers=_auth_header(tokens),
        )
        assert response.status_code == 502

    def test_test_channel_success(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        created = client.post(
            "/alert-channels",
            headers=_auth_header(tokens),
            json=_channel_payload(),
        ).json()["data"]

        sent: list[dict[str, object]] = []
        monkeypatch.setattr(
            alert_service,
            "_send_discord",
            lambda url, payload: sent.append(payload),
        )
        response = client.post(
            f"/alert-channels/{created['id']}/test",
            headers=_auth_header(tokens),
        )
        assert response.status_code == 200
        assert sent


class TestMetrics:
    def _fake_client(self) -> MagicMock:
        container = MagicMock()
        container.name = "infraforge-backend"
        container.labels = {
            "com.docker.compose.project": "infraforge",
            "com.docker.compose.service": "backend",
        }
        container.attrs = {
            "Config": {"Image": "infraforge-backend:latest"},
            "RestartCount": 3,
        }
        container.status = "running"

        client = MagicMock()
        client.containers.list.return_value = [container]
        return client

    def test_collect_exports_container_metrics(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            metrics_service.container_service,
            "_get_client",
            lambda: self._fake_client(),
        )
        metrics_service.collect()
        output = generate_latest(metrics_service.REGISTRY).decode()

        assert "infraforge_docker_available 1.0" in output
        assert 'name="infraforge-backend"' in output
        assert 'compose_project="infraforge"' in output
        assert "infraforge_container_restart_count" in output
        assert " 3.0" in output

    def test_collect_marks_docker_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail() -> None:
            raise RuntimeError("docker down")

        monkeypatch.setattr(
            metrics_service.container_service, "_get_client", _fail
        )
        metrics_service.collect()
        output = generate_latest(metrics_service.REGISTRY).decode()
        assert "infraforge_docker_available 0.0" in output

    def test_metrics_endpoint(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(metrics_service, "collect", lambda: None)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
