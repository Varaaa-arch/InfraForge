"""Test notifikasi deployment CI/CD ke channel alert."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.config import settings
from app.models.deployment import DeploymentStatus
from app.services import deployment_notification_service as service
from app.services.deployment_notification_service import DeploymentNotification


def _notification(
    *,
    event: str = "success",
    severity: str = "info",
) -> DeploymentNotification:
    started = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    return DeploymentNotification(
        deployment_id=12,
        event=event,
        severity=severity,
        application_name="backend-api",
        project_name="Demo",
        branch="main",
        trigger_source="ci_token",
        commit_sha="deadbeef12345678",
        started_at=started,
        finished_at=started + timedelta(seconds=75),
    )


class TestBuilders:
    def test_discord_payload_contains_deployment_details(self) -> None:
        payload = service.build_discord_payload(_notification())

        embed = payload["embeds"][0]  # type: ignore[index]
        assert embed["color"] == service.DEPLOY_COLORS["success"]
        assert "backend-api" in embed["title"]
        assert any(field["name"] == "Commit" for field in embed["fields"])

    def test_discord_failed_uses_red_color(self) -> None:
        payload = service.build_discord_payload(
            _notification(event="failed", severity="critical")
        )

        embed = payload["embeds"][0]  # type: ignore[index]
        assert embed["color"] == service.DEPLOY_COLORS["failed"]

    def test_slack_payload_uses_event_color(self) -> None:
        payload = service.build_slack_payload(_notification(event="queued"))

        attachment = payload["attachments"][0]  # type: ignore[index]
        assert attachment["color"] == service.DEPLOY_HEX_COLORS["queued"]
        assert "backend-api" in payload["text"]

    def test_telegram_message_contains_branch_and_commit(self) -> None:
        message = service.build_telegram_message(_notification())

        assert "backend-api" in message
        assert "main" in message
        assert "deadbeef" in message
        assert "1 menit 15 detik" in message


class TestNotify:
    def _context(
        self,
        *,
        status: DeploymentStatus = DeploymentStatus.pending,
        trigger_source: str = "ci_token",
    ) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
        deployment = MagicMock()
        deployment.id = 12
        deployment.application_id = 3
        deployment.status = status
        deployment.trigger_source = trigger_source
        deployment.branch = "main"
        deployment.commit_sha = "deadbeef12345678"
        deployment.started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        deployment.finished_at = (
            deployment.started_at + timedelta(seconds=30)
            if status in (DeploymentStatus.success, DeploymentStatus.failed)
            else None
        )

        application = MagicMock()
        application.name = "backend-api"
        application.project_id = 4

        project = MagicMock()
        project.name = "Demo"

        db = MagicMock()
        db.__enter__ = MagicMock(return_value=db)
        db.__exit__ = MagicMock(return_value=False)
        return deployment, application, project, db

    def test_queued_dispatches_info_notification(self) -> None:
        deployment, application, project, db = self._context()
        channel = MagicMock()

        with (
            patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", True),
            patch.object(service, "SessionLocal", return_value=db),
            patch.object(
                service.deployment_repository,
                "get_by_id",
                return_value=deployment,
            ),
            patch.object(
                service.application_repository,
                "get_by_id",
                return_value=application,
            ),
            patch.object(
                service.project_service,
                "get_project_by_id",
                return_value=project,
            ),
            patch.object(
                service.alert_channel_repository,
                "list_enabled_for_severity",
                return_value=[channel],
            ),
            patch.object(service, "_send_to_channel") as send,
        ):
            service.notify_queued(12)

        send.assert_called_once()
        sent = send.call_args.args[1]
        assert sent.event == "queued"
        assert sent.severity == "info"
        assert sent.application_name == "backend-api"

    def test_disabled_notification_does_not_open_session(self) -> None:
        with (
            patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", False),
            patch.object(service, "SessionLocal") as session_local,
        ):
            service.notify_queued(12)
            service.notify_finished(12)

        session_local.assert_not_called()

    def test_manual_deployment_is_skipped(self) -> None:
        deployment, application, project, db = self._context(
            trigger_source="manual"
        )

        with (
            patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", True),
            patch.object(service, "SessionLocal", return_value=db),
            patch.object(
                service.deployment_repository,
                "get_by_id",
                return_value=deployment,
            ),
            patch.object(
                service.application_repository,
                "get_by_id",
                return_value=application,
            ),
            patch.object(
                service.project_service,
                "get_project_by_id",
                return_value=project,
            ),
            patch.object(service, "_send_to_channel") as send,
        ):
            service.notify_queued(12)

        send.assert_not_called()

    def test_queued_skips_already_finished_deployment(self) -> None:
        deployment, application, project, db = self._context(
            status=DeploymentStatus.success
        )

        with (
            patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", True),
            patch.object(service, "SessionLocal", return_value=db),
            patch.object(
                service.deployment_repository,
                "get_by_id",
                return_value=deployment,
            ),
            patch.object(
                service.application_repository,
                "get_by_id",
                return_value=application,
            ),
            patch.object(
                service.project_service,
                "get_project_by_id",
                return_value=project,
            ),
            patch.object(service, "_send_to_channel") as send,
        ):
            service.notify_queued(12)

        send.assert_not_called()

    def test_finished_failed_uses_critical_severity(self) -> None:
        deployment, application, project, db = self._context(
            status=DeploymentStatus.failed
        )
        channel = MagicMock()

        with (
            patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", True),
            patch.object(service, "SessionLocal", return_value=db),
            patch.object(
                service.deployment_repository,
                "get_by_id",
                return_value=deployment,
            ),
            patch.object(
                service.application_repository,
                "get_by_id",
                return_value=application,
            ),
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
            patch.object(service, "_send_to_channel"),
        ):
            service.notify_finished(12)

        list_channels.assert_called_once_with(db, "critical")

    def test_channel_failure_is_best_effort(self) -> None:
        deployment, application, project, db = self._context()
        channel = MagicMock()

        with (
            patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", True),
            patch.object(service, "SessionLocal", return_value=db),
            patch.object(
                service.deployment_repository,
                "get_by_id",
                return_value=deployment,
            ),
            patch.object(
                service.application_repository,
                "get_by_id",
                return_value=application,
            ),
            patch.object(
                service.project_service,
                "get_project_by_id",
                return_value=project,
            ),
            patch.object(
                service.alert_channel_repository,
                "list_enabled_for_severity",
                return_value=[channel],
            ),
            patch.object(
                service,
                "_send_to_channel",
                side_effect=RuntimeError("webhook down"),
            ),
        ):
            service.notify_queued(12)

    def test_finished_pending_does_not_dispatch(self) -> None:
        deployment, application, project, db = self._context()

        with (
            patch.object(settings, "DEPLOY_NOTIFICATIONS_ENABLED", True),
            patch.object(service, "SessionLocal", return_value=db),
            patch.object(
                service.deployment_repository,
                "get_by_id",
                return_value=deployment,
            ),
            patch.object(
                service.application_repository,
                "get_by_id",
                return_value=application,
            ),
            patch.object(
                service.project_service,
                "get_project_by_id",
                return_value=project,
            ),
            patch.object(service, "_send_to_channel") as send,
        ):
            service.notify_finished(12)

        send.assert_not_called()


class TestQueueHook:
    def test_ci_deployment_notifies_finished(self) -> None:
        from app.services.deployment_queue import run_deployment_background

        deployment = MagicMock()
        deployment.id = 1
        deployment.trigger_source = "ci_token"
        deployment.status = DeploymentStatus.success
        application = MagicMock()
        application.id = 1
        server = MagicMock()
        server.id = 1

        with (
            patch("app.services.deployment_queue.redis_client") as redis_client,
            patch("app.services.deployment_queue.SessionLocal") as session_local,
            patch(
                "app.repositories.deployment_repository.get_by_id",
                return_value=deployment,
            ),
            patch(
                "app.repositories.application_repository.get_by_id",
                return_value=application,
            ),
            patch(
                "app.repositories.server_repository.get_by_id",
                return_value=server,
            ),
            patch("app.repositories.application_repository.update_status"),
            patch("app.services.deployment_service._run_deployment"),
            patch(
                "app.services.deployment_notification_service.notify_finished"
            ) as notify,
        ):
            redis_client.set.return_value = True
            db = MagicMock()
            db.__enter__ = MagicMock(return_value=db)
            db.__exit__ = MagicMock(return_value=False)
            session_local.return_value = db

            run_deployment_background(1, 1, 1)

        notify.assert_called_once_with(1)

    def test_manual_deployment_does_not_notify(self) -> None:
        from app.services.deployment_queue import run_deployment_background

        deployment = MagicMock()
        deployment.id = 1
        deployment.trigger_source = "manual"
        application = MagicMock()
        application.id = 1
        server = MagicMock()
        server.id = 1

        with (
            patch("app.services.deployment_queue.redis_client") as redis_client,
            patch("app.services.deployment_queue.SessionLocal") as session_local,
            patch(
                "app.repositories.deployment_repository.get_by_id",
                return_value=deployment,
            ),
            patch(
                "app.repositories.application_repository.get_by_id",
                return_value=application,
            ),
            patch(
                "app.repositories.server_repository.get_by_id",
                return_value=server,
            ),
            patch("app.repositories.application_repository.update_status"),
            patch("app.services.deployment_service._run_deployment"),
            patch(
                "app.services.deployment_notification_service.notify_finished"
            ) as notify,
        ):
            redis_client.set.return_value = True
            db = MagicMock()
            db.__enter__ = MagicMock(return_value=db)
            db.__exit__ = MagicMock(return_value=False)
            session_local.return_value = db

            run_deployment_background(1, 1, 1)

        notify.assert_not_called()
