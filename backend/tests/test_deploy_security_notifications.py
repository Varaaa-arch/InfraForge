"""Test notifikasi aktivitas token dan hasil webhook deployment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.config import settings
from app.services import deploy_security_notification_service as service


def _db_context() -> MagicMock:
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    return db


def test_token_created_sends_info_event() -> None:
    db = _db_context()
    channel = MagicMock()

    with (
        patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", True),
        patch.object(service, "SessionLocal", return_value=db),
        patch.object(
            service.alert_channel_repository,
            "list_enabled_for_severity",
            return_value=[channel],
        ) as list_channels,
        patch.object(service.alert_service, "send_to_channel") as send,
    ):
        service.notify_token_event(
            action="created",
            project_name="Demo",
            token_name="github-actions",
            prefix="dt_abcd1234",
            username="zenith",
        )

    list_channels.assert_called_once_with(db, "info")
    send.assert_called_once()
    event = send.call_args.args[1]
    assert event.alert_name == "DeployTokenCreated"
    assert event.status == "event"
    assert event.severity == "info"
    assert event.labels["token"] == "github-actions"
    assert "github-actions" in event.description


def test_token_revoked_uses_warning_severity() -> None:
    db = _db_context()
    channel = MagicMock()

    with (
        patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", True),
        patch.object(service, "SessionLocal", return_value=db),
        patch.object(
            service.alert_channel_repository,
            "list_enabled_for_severity",
            return_value=[channel],
        ) as list_channels,
        patch.object(service.alert_service, "send_to_channel"),
    ):
        service.notify_token_event(
            action="revoked",
            project_name="Demo",
            token_name="old-token",
            prefix="dt_deadbeef",
            username=None,
        )

    list_channels.assert_called_once_with(db, "warning")


def test_rejected_webhook_is_alerted_with_project_context() -> None:
    db = _db_context()
    channel = MagicMock()
    project = MagicMock()
    project.name = "Demo"

    with (
        patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", True),
        patch.object(service, "SessionLocal", return_value=db),
        patch.object(
            service.project_service,
            "get_project_by_id",
            return_value=project,
        ),
        patch.object(
            service.alert_channel_repository,
            "list_enabled_for_severity",
            return_value=[channel],
        ) as list_channels,
        patch.object(service.alert_service, "send_to_channel") as send,
    ):
        service.notify_webhook_outcome(
            outcome="invalid_signature",
            source="github",
            project_id=7,
            token_name="ci",
            branch="main",
            repository="https://github.com/acme/demo",
        )

    list_channels.assert_called_once_with(db, "warning")
    event = send.call_args.args[1]
    assert event.alert_name == "DeployWebhookRejected"
    assert event.severity == "warning"
    assert event.labels["outcome"] == "invalid_signature"
    assert event.labels["project"] == "Demo"


def test_ignored_branch_uses_info_severity() -> None:
    db = _db_context()
    channel = MagicMock()

    with (
        patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", True),
        patch.object(service, "SessionLocal", return_value=db),
        patch.object(
            service.alert_channel_repository,
            "list_enabled_for_severity",
            return_value=[channel],
        ) as list_channels,
        patch.object(service.alert_service, "send_to_channel"),
    ):
        service.notify_webhook_outcome(
            outcome="no_match",
            source="github",
            token_name="ci",
            branch="develop",
        )

    list_channels.assert_called_once_with(db, "info")


def test_scheduled_webhook_does_not_duplicate_notification() -> None:
    with (
        patch.object(service, "SessionLocal") as session_local,
        patch.object(service.alert_service, "send_to_channel") as send,
    ):
        service.notify_webhook_outcome(outcome="scheduled", source="github")

    session_local.assert_not_called()
    send.assert_not_called()


def test_notifications_can_be_disabled() -> None:
    with (
        patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", False),
        patch.object(service, "SessionLocal") as session_local,
    ):
        service.notify_token_event(
            action="rotated",
            project_name="Demo",
            token_name="ci",
            prefix="dt_abcd1234",
            username="zenith",
        )

    session_local.assert_not_called()
