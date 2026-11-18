"""Notifikasi deployment CI/CD ke channel alert yang sudah dikonfigurasi."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.database.session import SessionLocal
from app.models.alert import AlertChannel, AlertChannelType
from app.models.deployment import Deployment, DeploymentStatus, TriggerSource
from app.repositories import (
    alert_channel_repository,
    application_repository,
    deployment_repository,
)
from app.services import alert_channel_service, alert_service, project_service

NOTIFIABLE_SOURCES = {
    TriggerSource.ci_token.value,
    TriggerSource.github_webhook.value,
}

DEPLOY_COLORS = {
    "queued": 0x3B82F6,
    "success": 0x22C55E,
    "failed": 0xEF4444,
}
DEPLOY_HEX_COLORS = {
    "queued": "#3B82F6",
    "success": "#22C55E",
    "failed": "#EF4444",
}


@dataclass(frozen=True)
class DeploymentNotification:
    deployment_id: int
    event: str
    severity: str
    application_name: str
    project_name: str
    branch: str
    trigger_source: str
    commit_sha: str | None
    started_at: datetime
    finished_at: datetime | None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _short_commit(commit_sha: str | None) -> str:
    return commit_sha[:8] if commit_sha else "-"


def _duration(notification: DeploymentNotification) -> str:
    if notification.finished_at is None:
        return "-"
    seconds = max(
        0,
        int(
            (notification.finished_at - notification.started_at).total_seconds()
        ),
    )
    if seconds < 60:
        return f"{seconds} detik"
    minutes, remaining = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} menit {remaining} detik"
    hours, remaining_minutes = divmod(minutes, 60)
    return f"{hours} jam {remaining_minutes} menit"


def _build_notification(
    deployment: Deployment,
    application_name: str,
    project_name: str,
    *,
    event: str,
    severity: str,
) -> DeploymentNotification:
    return DeploymentNotification(
        deployment_id=deployment.id,
        event=event,
        severity=severity,
        application_name=application_name,
        project_name=project_name,
        branch=deployment.branch,
        trigger_source=deployment.trigger_source,
        commit_sha=deployment.commit_sha,
        started_at=deployment.started_at,
        finished_at=deployment.finished_at,
    )


def build_discord_payload(
    notification: DeploymentNotification,
) -> dict[str, object]:
    fields: list[dict[str, object]] = [
        {"name": "Project", "value": notification.project_name, "inline": True},
        {
            "name": "Application",
            "value": notification.application_name,
            "inline": True,
        },
        {"name": "Branch", "value": notification.branch, "inline": True},
        {
            "name": "Pemicu",
            "value": notification.trigger_source,
            "inline": True,
        },
        {
            "name": "Commit",
            "value": _short_commit(notification.commit_sha),
            "inline": True,
        },
        {
            "name": "Durasi",
            "value": _duration(notification),
            "inline": True,
        },
    ]
    embed: dict[str, object] = {
        "title": (
            f"[{notification.event.upper()}] Deployment "
            f"#{notification.deployment_id} · {notification.application_name}"
        )[:256],
        "description": (
            f"Deployment {notification.event} untuk "
            f"{notification.application_name}."
        ),
        "color": DEPLOY_COLORS.get(notification.event, 0x71717A),
        "fields": fields,
        "timestamp": _iso(notification.finished_at or notification.started_at),
        "footer": {"text": "InfraForge · Deployment"},
    }
    return {"username": "InfraForge Deployments", "embeds": [embed]}


def build_slack_payload(
    notification: DeploymentNotification,
) -> dict[str, object]:
    def esc(value: str | None) -> str:
        return html.escape(value or "-")

    blocks: list[dict[str, object]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": (
                    f"[{notification.event.upper()}] Deployment "
                    f"#{notification.deployment_id} · "
                    f"{notification.application_name}"
                )[:150],
                "emoji": False,
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Project:*\n{esc(notification.project_name)}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Application:*\n{esc(notification.application_name)}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Branch:*\n{esc(notification.branch)}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Pemicu:*\n{esc(notification.trigger_source)}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Commit:*\n{esc(_short_commit(notification.commit_sha))}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Durasi:*\n{esc(_duration(notification))}",
                },
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"InfraForge · Deployment · "
                        f"{esc(_iso(notification.finished_at or notification.started_at))}"
                    ),
                }
            ],
        },
    ]
    return {
        "text": (
            f"[{notification.event.upper()}] Deployment "
            f"#{notification.deployment_id} — {notification.application_name}"
        ),
        "attachments": [
            {
                "color": DEPLOY_HEX_COLORS.get(notification.event, "#71717A"),
                "blocks": blocks,
            }
        ],
    }


def build_telegram_message(notification: DeploymentNotification) -> str:
    def esc(value: str | None) -> str:
        return html.escape(value or "-")

    lines = [
        (
            f"<b>[{esc(notification.event.upper())}] Deployment "
            f"#{notification.deployment_id} · "
            f"{esc(notification.application_name)}</b>"
        ),
        f"Project: {esc(notification.project_name)}",
        f"Branch: {esc(notification.branch)}",
        f"Pemicu: {esc(notification.trigger_source)}",
        f"Commit: {esc(_short_commit(notification.commit_sha))}",
        f"Durasi: {esc(_duration(notification))}",
        f"Waktu: {esc(_iso(notification.finished_at or notification.started_at))}",
    ]
    return "\n".join(lines)[:4000]


def _send_to_channel(
    channel: AlertChannel, notification: DeploymentNotification
) -> None:
    channel_type = AlertChannelType(channel.channel_type)
    if channel_type == AlertChannelType.discord:
        webhook_url = alert_channel_service.decrypt_discord_webhook_url(channel)
        if not webhook_url:
            raise RuntimeError("Discord webhook URL belum dikonfigurasi")
        alert_service.send_discord(
            webhook_url, build_discord_payload(notification)
        )
        return

    if channel_type == AlertChannelType.slack:
        webhook_url = alert_channel_service.decrypt_slack_webhook_url(channel)
        if not webhook_url:
            raise RuntimeError("Slack webhook URL belum dikonfigurasi")
        alert_service.send_slack(webhook_url, build_slack_payload(notification))
        return

    bot_token = alert_channel_service.decrypt_telegram_bot_token(channel)
    if not bot_token or not channel.telegram_chat_id:
        raise RuntimeError("Bot token / chat ID Telegram belum dikonfigurasi")
    alert_service.send_telegram(
        bot_token,
        channel.telegram_chat_id,
        build_telegram_message(notification),
    )


def _dispatch(db: Session, notification: DeploymentNotification) -> None:
    channels = alert_channel_repository.list_enabled_for_severity(
        db, notification.severity
    )
    if not channels:
        logger.debug(
            f"Tidak ada channel alert untuk notifikasi deployment "
            f"#{notification.deployment_id} ({notification.event})."
        )
        return

    for channel in channels:
        try:
            _send_to_channel(channel, notification)
            logger.info(
                f"Notifikasi deployment #{notification.deployment_id} "
                f"({notification.event}) dikirim ke channel {channel.name}."
            )
        except Exception as exc:
            logger.error(
                f"Gagal mengirim notifikasi deployment "
                f"#{notification.deployment_id} ke channel {channel.name}: {exc}"
            )


def _load_context(
    db: Session, deployment_id: int
) -> tuple[Deployment, str, str] | None:
    deployment = deployment_repository.get_by_id(db, deployment_id)
    if deployment is None:
        return None
    if deployment.trigger_source not in NOTIFIABLE_SOURCES:
        return None

    application = application_repository.get_by_id(
        db, deployment.application_id
    )
    if application is None:
        return None

    project = project_service.get_project_by_id(db, application.project_id)
    project_name = (
        project.name if project is not None else f"Project #{application.project_id}"
    )
    return deployment, application.name, project_name


def notify_queued(deployment_id: int) -> None:
    if not settings.DEPLOY_NOTIFICATIONS_ENABLED:
        return
    try:
        with SessionLocal() as db:
            context = _load_context(db, deployment_id)
            if context is None:
                return
            deployment, application_name, project_name = context
            if deployment.status != DeploymentStatus.pending:
                return
            notification = _build_notification(
                deployment,
                application_name,
                project_name,
                event="queued",
                severity="info",
            )
            _dispatch(db, notification)
    except Exception as exc:
        logger.error(
            f"Gagal menyiapkan notifikasi queued deployment "
            f"#{deployment_id}: {exc}"
        )


def notify_finished(deployment_id: int) -> None:
    if not settings.DEPLOY_NOTIFICATIONS_ENABLED:
        return
    try:
        with SessionLocal() as db:
            context = _load_context(db, deployment_id)
            if context is None:
                return
            deployment, application_name, project_name = context
            if deployment.status not in (
                DeploymentStatus.success,
                DeploymentStatus.failed,
            ):
                return
            failed = deployment.status == DeploymentStatus.failed
            notification = _build_notification(
                deployment,
                application_name,
                project_name,
                event=deployment.status.value,
                severity="critical" if failed else "info",
            )
            _dispatch(db, notification)
    except Exception as exc:
        logger.error(
            f"Gagal menyiapkan notifikasi hasil deployment "
            f"#{deployment_id}: {exc}"
        )
