"""
Model SQLAlchemy untuk tabel `applications`.

Setiap aplikasi merupakan unit deployable yang dimiliki oleh sebuah project.
Satu project bisa memiliki banyak aplikasi (one-to-many).

Kolom deployment config (dockerfile_path, compose_path, build_context, branch)
menyimpan informasi yang dibutuhkan oleh deployment engine nanti.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class AppStatus(str, enum.Enum):
    idle = "idle"
    deploying = "deploying"
    running = "running"
    failed = "failed"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Identitas aplikasi ---
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Nama aplikasi, misal: backend-api, frontend-web",
    )

    # --- Deployment Config (Task 3.10) ---
    repository: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="URL repository Git aplikasi ini",
    )
    branch: Mapped[str] = mapped_column(
        String(100),
        default="main",
        server_default="main",
        nullable=False,
        comment="Branch yang akan di-deploy",
    )
    dockerfile_path: Mapped[str] = mapped_column(
        String(255),
        default="Dockerfile",
        server_default="Dockerfile",
        nullable=False,
        comment="Path ke Dockerfile relatif dari root repository",
    )
    compose_path: Mapped[str] = mapped_column(
        String(255),
        default="docker-compose.yml",
        server_default="docker-compose.yml",
        nullable=False,
        comment="Path ke docker-compose file relatif dari root repository",
    )
    build_context: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Docker build context path (opsional, default: direktori Dockerfile)",
    )

    # --- Status operasional ---
    status: Mapped[AppStatus] = mapped_column(
        Enum(AppStatus, name="app_status", values_callable=lambda e: [m.value for m in e]),
        default=AppStatus.idle,
        server_default=AppStatus.idle.value,
        nullable=False,
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
