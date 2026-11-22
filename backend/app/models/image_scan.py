"""Model hasil pemindaian kerentanan image container (Trivy)."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ImageScanStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ImageScan(Base):
    __tablename__ = "image_scans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Project terkait (opsional); dihapus bersama project",
    )
    image_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="Referensi image yang dipindai, mis. nginx:1.27",
    )
    image_digest: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="ImageID/digest yang dilaporkan scanner",
    )
    status: Mapped[ImageScanStatus] = mapped_column(
        Enum(
            ImageScanStatus,
            name="image_scan_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ImageScanStatus.pending,
        server_default=ImageScanStatus.pending.value,
        nullable=False,
    )
    overall_severity: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Severity tertinggi: critical/high/medium/low/none/unknown",
    )
    critical_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    high_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    medium_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    low_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    total_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    findings: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Daftar temuan CVE ringkas (dibatasi IMAGE_SCAN_MAX_FINDINGS)",
    )
    scanner: Mapped[str] = mapped_column(
        String(50), default="trivy", server_default="trivy", nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(
        String(160), nullable=True, comment="Username pemicu scan"
    )
    scanned_at: Mapped[datetime | None] = mapped_column(
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
