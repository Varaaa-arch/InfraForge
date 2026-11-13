"""Schema Pydantic untuk alerting (webhook Alertmanager + channel notifikasi)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.alert import AlertChannelType, AlertStatus


class AlertmanagerAlert(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    status: Literal["firing", "resolved"]
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    generator_url: str | None = Field(default=None, alias="generatorURL")
    fingerprint: str


class AlertmanagerPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: str = "4"
    status: Literal["firing", "resolved"] = "firing"
    receiver: str = ""
    group_key: str = Field(default="", alias="groupKey")
    alerts: list[AlertmanagerAlert]


class AlertIngestResponse(BaseModel):
    received: int
    created: int
    resolved: int


class AlertEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fingerprint: str
    alert_name: str
    status: AlertStatus
    severity: str
    summary: str | None
    description: str | None
    labels: dict[str, str]
    annotations: dict[str, str]
    starts_at: datetime
    ends_at: datetime | None
    created_at: datetime


class AlertChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AlertChannelType
    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_config(self) -> AlertChannelCreate:
        _validate_channel_config(
            self.type,
            self.discord_webhook_url,
            self.telegram_bot_token,
            self.telegram_chat_id,
        )
        return self


class AlertChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    enabled: bool | None = None


class AlertChannelResponse(BaseModel):
    id: int
    name: str
    type: AlertChannelType
    enabled: bool
    has_discord_webhook: bool
    has_telegram_bot_token: bool
    telegram_chat_id: str | None
    created_at: datetime
    updated_at: datetime


def _validate_channel_config(
    channel_type: AlertChannelType,
    discord_webhook_url: str | None,
    telegram_bot_token: str | None,
    telegram_chat_id: str | None,
) -> None:
    if channel_type == AlertChannelType.discord:
        if not discord_webhook_url or not discord_webhook_url.startswith(
            ("http://", "https://")
        ):
            raise ValueError(
                "discord_webhook_url wajib diisi dan harus diawali http:// atau https://"
            )
        return

    if not telegram_bot_token:
        raise ValueError("telegram_bot_token wajib diisi untuk channel Telegram")
    if not telegram_chat_id:
        raise ValueError("telegram_chat_id wajib diisi untuk channel Telegram")


validate_channel_config = _validate_channel_config
