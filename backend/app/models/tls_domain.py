"""Model konfigurasi domain TLS/SSL dan riwayat pemeriksaan sertifikat."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class TlsDomainStatus(str, enum.Enum):
    pending = "pending"
    healthy = "healthy"
    expiring = "expiring"
    expired = "expired"
    invalid = "invalid"
    error = "error"


class TlsDomain(Base):
    __tablename__ = "tls_domains"
    __table_args__ = (
        UniqueConstraint("host", "port", name="uq_tls_domains_host_port"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Label ramah untuk target"
    )
    host: Mapped[str] = mapped_column(
        String(253), nullable=False, comment="Hostname atau alamat IP target"
    )
    port: Mapped[int] = mapped_column(
        Integer, default=443, server_default="443", nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    warning_days: Mapped[int] = mapped_column(
        Integer,
        default=30,
        server_default="30",
        nullable=False,
        comment="Ambang hari sebelum expiry dianggap expiring",
    )
    status: Mapped[TlsDomainStatus] = mapped_column(
        Enum(
            TlsDomainStatus,
            name="tls_domain_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=TlsDomainStatus.pending,
        server_default=TlsDomainStatus.pending.value,
        nullable=False,
    )
    days_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expiry_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    protocol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trusted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_alerted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    alerted_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TlsDomainCheck(Base):
    __tablename__ = "tls_domain_checks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tls_domain_id: Mapped[int] = mapped_column(
        ForeignKey("tls_domains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    days_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expiry_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    protocol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trusted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_sent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
