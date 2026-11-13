"""Service alerting: ingest webhook Alertmanager, riwayat, dan notifikasi."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.database.session import SessionLocal
from app.models.alert import AlertChannel, AlertChannelType, AlertEvent, AlertStatus
from app.repositories import alert_channel_repository, alert_repository
from app.schemas.alert import AlertmanagerAlert, AlertmanagerPayload
from app.services import alert_channel_service

SEVERITY_COLORS = {
    "critical": 0xEF4444,
    "warning": 0xF59E0B,
    "info": 0x3B82F6,
}
RESOLVED_COLOR = 0x22C55E
DISCORD_USERNAME = "InfraForge Alerts"


@dataclass
class NotificationEvent:
    alert_name: str
    status: str
    severity: str
    summary: str | None
    description: str | None
    labels: dict[str, str]
    annotations: dict[str, str]
    starts_at: datetime
    ends_at: datetime | None


@dataclass
class IngestResult:
    received: int
    created: int
    resolved: int
    event_ids: list[int]


def _notification_event(event: AlertEvent) -> NotificationEvent:
    return NotificationEvent(
        alert_name=event.alert_name,
        status=event.status.value,
        severity=event.severity,
        summary=event.summary,
        description=event.description,
        labels=dict(event.labels or {}),
        annotations=dict(event.annotations or {}),
        starts_at=event.starts_at,
        ends_at=event.ends_at,
    )


def _alert_name(alert: AlertmanagerAlert) -> str:
    return alert.labels.get("alertname") or f"alert-{alert.fingerprint[:12]}"


def list_events(
    db: Session,
    *,
    status: AlertStatus | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AlertEvent]:
    return alert_repository.list_events(
        db,
        status=status,
        severity=severity,
        limit=limit,
        offset=offset,
    )


def ingest(db: Session, payload: AlertmanagerPayload) -> IngestResult:
    created = 0
    resolved = 0
    event_ids: list[int] = []

    for alert in payload.alerts:
        if alert.status == "firing":
            existing = alert_repository.get_open_by_fingerprint(db, alert.fingerprint)
            if existing is not None:
                continue
            event = alert_repository.create(
                db,
                fingerprint=alert.fingerprint,
                alert_name=_alert_name(alert),
                status=AlertStatus.firing,
                severity=alert.labels.get("severity", "unknown"),
                summary=alert.annotations.get("summary"),
                description=alert.annotations.get("description"),
                labels=alert.labels,
                annotations=alert.annotations,
                starts_at=alert.starts_at,
                ends_at=alert.ends_at,
            )
            created += 1
            event_ids.append(event.id)
            continue

        existing = alert_repository.get_open_by_fingerprint(db, alert.fingerprint)
        if existing is None:
            continue
        event = alert_repository.resolve(
            db,
            existing,
            alert.ends_at or datetime.now(timezone.utc),
        )
        resolved += 1
        event_ids.append(event.id)

    return IngestResult(
        received=len(payload.alerts),
        created=created,
        resolved=resolved,
        event_ids=event_ids,
    )


def dispatch_event_notifications(event_ids: list[int]) -> None:
    if not event_ids:
        return

    with SessionLocal() as db:
        events = [
            event
            for event_id in event_ids
            if (event := alert_repository.get_by_id(db, event_id)) is not None
        ]
        channels = alert_channel_repository.list_enabled(db)
        for event in events:
            notification = _notification_event(event)
            for channel in channels:
                try:
                    send_to_channel(channel, notification)
                    logger.info(
                        f"Alert '{event.alert_name}' ({event.status.value}) "
                        f"dikirim ke channel {channel.name}."
                    )
                except Exception as exc:
                    logger.error(
                        f"Gagal mengirim alert '{event.alert_name}' "
                        f"ke channel {channel.name}: {exc}"
                    )


def send_to_channel(channel: AlertChannel, event: NotificationEvent) -> None:
    channel_type = AlertChannelType(channel.channel_type)
    if channel_type == AlertChannelType.discord:
        webhook_url = alert_channel_service.decrypt_discord_webhook_url(channel)
        if not webhook_url:
            raise RuntimeError("Discord webhook URL belum dikonfigurasi")
        _send_discord(webhook_url, build_discord_payload(event))
        return

    bot_token = alert_channel_service.decrypt_telegram_bot_token(channel)
    if not bot_token or not channel.telegram_chat_id:
        raise RuntimeError("Bot token / chat ID Telegram belum dikonfigurasi")
    _send_telegram(
        bot_token,
        channel.telegram_chat_id,
        build_telegram_message(event),
    )


def build_discord_payload(event: NotificationEvent) -> dict[str, object]:
    color = (
        RESOLVED_COLOR
        if event.status == AlertStatus.resolved.value
        else SEVERITY_COLORS.get(event.severity.lower(), 0x71717A)
    )
    fields: list[dict[str, object]] = [
        {"name": "Severity", "value": event.severity or "unknown", "inline": True},
        {"name": "Status", "value": event.status, "inline": True},
    ]
    for key in ("container", "service", "instance", "job"):
        value = event.labels.get(key)
        if value:
            fields.append({"name": key.capitalize(), "value": value, "inline": True})

    embed: dict[str, object] = {
        "title": f"[{event.status.upper()}] {event.alert_name}",
        "description": event.description or event.summary or "",
        "color": color,
        "fields": fields[:6],
        "timestamp": event.starts_at.isoformat(),
        "footer": {"text": "InfraForge · Alertmanager"},
    }
    return {"username": DISCORD_USERNAME, "embeds": [embed]}


def build_telegram_message(event: NotificationEvent) -> str:
    def esc(value: str | None) -> str:
        return html.escape(value or "-")

    lines = [
        f"<b>[{esc(event.status.upper())}] {esc(event.alert_name)}</b>",
        f"Severity: {esc(event.severity)}",
    ]
    for key in ("container", "service", "instance", "job"):
        value = event.labels.get(key)
        if value:
            lines.append(f"{key.capitalize()}: {esc(value)}")
    if event.description or event.summary:
        lines.append("")
        lines.append(esc(event.description or event.summary))
    lines.append("")
    lines.append(f"Waktu: {esc(event.starts_at.isoformat())}")
    return "\n".join(lines)[:4000]


def _send_discord(webhook_url: str, payload: dict[str, object]) -> None:
    response = httpx.post(
        webhook_url,
        json=payload,
        timeout=settings.ALERT_REQUEST_TIMEOUT,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Discord HTTP {response.status_code}: {response.text[:200]}"
        )


def _send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    response = httpx.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        },
        timeout=settings.ALERT_REQUEST_TIMEOUT,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Telegram HTTP {response.status_code}: {response.text[:200]}"
        )


def send_test(channel: AlertChannel) -> None:
    event = NotificationEvent(
        alert_name="Test Notifikasi InfraForge",
        status=AlertStatus.firing.value,
        severity="info",
        summary="Channel berhasil terhubung ke InfraForge Alerting.",
        description=(
            "Ini adalah pesan uji dari dashboard InfraForge. "
            "Jika kamu menerima pesan ini, konfigurasi channel sudah benar."
        ),
        labels={"instance": "infraforge", "service": "alertmanager"},
        annotations={},
        starts_at=datetime.now(timezone.utc),
        ends_at=None,
    )
    send_to_channel(channel, event)
