"""Repository untuk tabel `alert_channels`."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.alert import AlertChannel, AlertChannelType, severity_rank


def list_all(db: Session) -> list[AlertChannel]:
    return db.query(AlertChannel).order_by(AlertChannel.name.asc()).all()


def list_enabled(db: Session) -> list[AlertChannel]:
    return (
        db.query(AlertChannel)
        .filter(AlertChannel.enabled.is_(True))
        .order_by(AlertChannel.name.asc())
        .all()
    )


def list_enabled_for_severity(db: Session, severity: str | None) -> list[AlertChannel]:
    """Channel aktif yang threshold-nya terpenuhi oleh severity event."""
    rank = severity_rank(severity)
    return [
        channel
        for channel in list_enabled(db)
        if severity_rank(channel.min_severity) <= rank
    ]


def get_by_id(db: Session, channel_id: int) -> AlertChannel | None:
    return db.get(AlertChannel, channel_id)


def create(
    db: Session,
    *,
    name: str,
    channel_type: AlertChannelType,
    encrypted_discord_webhook_url: str | None,
    encrypted_telegram_bot_token: str | None,
    telegram_chat_id: str | None,
    encrypted_slack_webhook_url: str | None,
    min_severity: str,
    enabled: bool,
) -> AlertChannel:
    channel = AlertChannel(
        name=name,
        channel_type=channel_type,
        encrypted_discord_webhook_url=encrypted_discord_webhook_url,
        encrypted_telegram_bot_token=encrypted_telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        encrypted_slack_webhook_url=encrypted_slack_webhook_url,
        min_severity=min_severity,
        enabled=enabled,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def save(db: Session, channel: AlertChannel) -> AlertChannel:
    db.commit()
    db.refresh(channel)
    return channel


def delete(db: Session, channel: AlertChannel) -> None:
    db.delete(channel)
    db.commit()
