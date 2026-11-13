"""Service untuk CRUD channel notifikasi alert."""

from __future__ import annotations

from app.models.alert import AlertChannel, AlertChannelType
from app.repositories import alert_channel_repository
from app.schemas.alert import (
    AlertChannelCreate,
    AlertChannelResponse,
    AlertChannelUpdate,
    validate_channel_config,
)
from app.services import encryption_service
from sqlalchemy.orm import Session


def list_channels(db: Session) -> list[AlertChannel]:
    return alert_channel_repository.list_all(db)


def get_channel(db: Session, channel_id: int) -> AlertChannel | None:
    return alert_channel_repository.get_by_id(db, channel_id)


def create_channel(db: Session, payload: AlertChannelCreate) -> AlertChannel:
    return alert_channel_repository.create(
        db,
        name=payload.name.strip(),
        channel_type=payload.type,
        encrypted_discord_webhook_url=(
            encryption_service.encrypt(payload.discord_webhook_url)
            if payload.discord_webhook_url
            else None
        ),
        encrypted_telegram_bot_token=(
            encryption_service.encrypt(payload.telegram_bot_token)
            if payload.telegram_bot_token
            else None
        ),
        telegram_chat_id=payload.telegram_chat_id,
        enabled=payload.enabled,
    )


def update_channel(
    db: Session, channel: AlertChannel, payload: AlertChannelUpdate
) -> AlertChannel:
    if payload.name is not None:
        channel.name = payload.name.strip()
    if payload.enabled is not None:
        channel.enabled = payload.enabled
    if payload.telegram_chat_id is not None:
        channel.telegram_chat_id = payload.telegram_chat_id
    if payload.discord_webhook_url is not None:
        channel.encrypted_discord_webhook_url = encryption_service.encrypt(
            payload.discord_webhook_url
        )
    if payload.telegram_bot_token is not None:
        channel.encrypted_telegram_bot_token = encryption_service.encrypt(
            payload.telegram_bot_token
        )

    validate_channel_config(
        channel.channel_type,
        decrypt_discord_webhook_url(channel),
        decrypt_telegram_bot_token(channel),
        channel.telegram_chat_id,
    )
    return alert_channel_repository.save(db, channel)


def delete_channel(db: Session, channel: AlertChannel) -> None:
    alert_channel_repository.delete(db, channel)


def decrypt_discord_webhook_url(channel: AlertChannel) -> str | None:
    if not channel.encrypted_discord_webhook_url:
        return None
    return encryption_service.decrypt(channel.encrypted_discord_webhook_url)


def decrypt_telegram_bot_token(channel: AlertChannel) -> str | None:
    if not channel.encrypted_telegram_bot_token:
        return None
    return encryption_service.decrypt(channel.encrypted_telegram_bot_token)


def to_response(channel: AlertChannel) -> AlertChannelResponse:
    return AlertChannelResponse(
        id=channel.id,
        name=channel.name,
        type=AlertChannelType(channel.channel_type),
        enabled=channel.enabled,
        has_discord_webhook=bool(channel.encrypted_discord_webhook_url),
        has_telegram_bot_token=bool(channel.encrypted_telegram_bot_token),
        telegram_chat_id=channel.telegram_chat_id,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )
