"""Model untuk alerting: channel notifikasi dan riwayat alert."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class AlertChannelType(str, enum.Enum):
    discord = "discord"
    telegram = "telegram"


class AlertStatus(str, enum.Enum):
    firing = "firing"
    resolved = "resolved"


class AlertChannel(Base):
    __tablename__ = "alert_channels"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel_type: Mapped[AlertChannelType] = mapped_column(
        "type",
        Enum(
            AlertChannelType,
            name="alert_channel_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    encrypted_discord_webhook_url: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    encrypted_telegram_bot_token: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    telegram_chat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    alert_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        Enum(
            AlertStatus,
            name="alert_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(20), default="unknown", server_default="unknown", nullable=False
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    annotations: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
