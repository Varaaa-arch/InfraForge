"""Model policy resource dan auto-healing per container."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ContainerPolicy(Base):
    """Policy yang disimpan per nama container Docker.

    ``container_name`` dipakai sebagai kunci karena container bisa di-recreate
    oleh ``docker compose`` dengan ID baru sementara namanya tetap.
    """

    __tablename__ = "container_policies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    container_name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    container_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    compose_project: Mapped[str | None] = mapped_column(String(100), nullable=True)
    compose_service: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Resource limit (None/0 = tanpa limit)
    cpu_limit_cores: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpu_period: Mapped[int] = mapped_column(
        Integer, default=100_000, server_default="100000", nullable=False
    )
    memory_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Auto-restart & auto-healing
    restart_policy: Mapped[str] = mapped_column(
        String(20), default="no", server_default="no", nullable=False
    )
    auto_heal_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    unhealthy_threshold: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    max_restarts: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    restart_cooldown_seconds: Mapped[int] = mapped_column(
        Integer, default=300, server_default="300", nullable=False
    )

    # Status runtime yang diperbarui poller
    unhealthy_streak: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    last_health_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_restart_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    restart_count_window: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    window_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    applied_at: Mapped[datetime | None] = mapped_column(
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
