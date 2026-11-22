"""Notifikasi aktivitas deployment token dan hasil webhook ke channel alert.

Notifikasi bersifat best-effort dan mengikuti channel aktif yang threshold
severity-nya terpenuhi. Event ini tidak membuat baris ``alert_events`` baru;
audit tetap menjadi sumber riwayat utama.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from app.config import settings
from app.database.session import SessionLocal
from app.models.alert import AlertChannel
from app.repositories import alert_channel_repository
from app.services import alert_service, project_service

TOKEN_ACTIONS = {
    "created": ("DeployTokenCreated", "info", "Deployment token dibuat"),
    "rotated": ("DeployTokenRotated", "info", "Deployment token dirotasi"),
    "revoked": ("DeployTokenRevoked", "warning", "Deployment token dicabut"),
}

WEBHOOK_SEVERITIES = {
    "invalid_token": "warning",
    "invalid_signature": "warning",
    "invalid_payload": "warning",
    "invalid_target": "warning",
    "conflict": "warning",
    "duplicate": "info",
    "ignored_event": "info",
    "no_target": "warning",
    "no_match": "info",
    "locked": "info",
    "partial": "info",
}


def _dispatch(
    *,
    alert_name: str,
    severity: str,
    summary: str,
    description: str,
    labels: dict[str, str],
) -> None:
    if not settings.DEPLOY_NOTIFICATIONS_ENABLED:
        return

    try:
        with SessionLocal() as db:
            channels: list[AlertChannel] = (
                alert_channel_repository.list_enabled_for_severity(db, severity)
            )
            if not channels:
                return

            event = alert_service.NotificationEvent(
                alert_name=alert_name,
                status="event",
                severity=severity,
                summary=summary,
                description=description,
                labels=labels,
                annotations={},
                starts_at=datetime.now(timezone.utc),
                ends_at=None,
            )
            for channel in channels:
                try:
                    alert_service.send_to_channel(channel, event)
                    logger.info(
                        f"Notifikasi {alert_name} dikirim ke channel {channel.name}."
                    )
                except Exception as exc:
                    logger.error(
                        f"Gagal mengirim notifikasi {alert_name} "
                        f"ke channel {channel.name}: {exc}"
                    )
    except Exception as exc:
        logger.error(f"Gagal menyiapkan notifikasi {alert_name}: {exc}")


def notify_token_event(
    *,
    action: str,
    project_name: str,
    token_name: str,
    prefix: str,
    username: str | None,
) -> None:
    """Kirim notifikasi pembuatan, rotasi, atau pencabutan token."""
    metadata = TOKEN_ACTIONS.get(action)
    if metadata is None:
        return
    alert_name, severity, title = metadata
    actor = username or "sistem"
    _dispatch(
        alert_name=alert_name,
        severity=severity,
        summary=f"{title}: {token_name}",
        description=(
            f"{title} pada project {project_name} oleh {actor}. "
            f"Token: {token_name}. Prefix: {prefix}."
        ),
        labels={
            "event": action,
            "project": project_name,
            "token": token_name,
            "prefix": prefix,
            "actor": actor,
        },
    )


def notify_webhook_outcome(
    *,
    outcome: str,
    source: str,
    project_id: int | None = None,
    token_name: str | None = None,
    branch: str | None = None,
    repository: str | None = None,
) -> None:
    """Kirim notifikasi webhook yang ditolak/diabaikan atau diproses sebagian."""
    if outcome == "scheduled":
        return

    severity = WEBHOOK_SEVERITIES.get(outcome, "warning")
    project_name = "Tidak diketahui"
    if project_id is not None:
        with SessionLocal() as db:
            project = project_service.get_project_by_id(db, project_id)
            if project is not None:
                project_name = project.name

    details = [f"source={source}", f"outcome={outcome}"]
    if branch:
        details.append(f"branch={branch}")
    if repository:
        details.append(f"repository={repository}")
    if token_name:
        details.append(f"token={token_name}")

    _dispatch(
        alert_name="DeployWebhookRejected",
        severity=severity,
        summary=f"Webhook deployment {outcome}",
        description=(
            f"Event webhook dari {source} tidak dijalankan untuk project "
            f"{project_name}: {', '.join(details)}."
        ),
        labels={
            "event": "webhook",
            "outcome": outcome,
            "source": source,
            "project": project_name,
            **({"branch": branch} if branch else {}),
            **({"repository": repository} if repository else {}),
        },
    )
