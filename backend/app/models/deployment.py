"""
Model SQLAlchemy untuk tabel `deployments`.

Setiap baris merepresentasikan satu eksekusi deployment dari sebuah aplikasi
ke sebuah server. Status bergerak dari pending → deploying → success/failed.

Kolom rollback:
  - rollback_of        : FK ke deployment.id yang menjadi target rollback.
                         NULL jika bukan rollback.
  - compose_path_snapshot: Snapshot path compose_file saat deployment sukses,
                         dipakai oleh rollback untuk re-deploy konfigurasi lama.
  - is_rollback        : True jika deployment ini adalah hasil operasi rollback.

Metadata versi:
  - tag            : Git tag yang menunjuk tepat ke commit deployment, jika ada.
  - triggered_by   : Identitas pemicu (username, deploy-token:<nama>, webhook).

Relasi:
  - application_id → FK ke tabel applications (CASCADE delete)
  - server_id      → FK ke tabel servers (SET NULL saat server dihapus, agar
                     history deployment tidak ikut hilang)
  - rollback_of    → FK ke deployments.id (SET NULL jika target dihapus)
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class DeploymentStatus(str, enum.Enum):
    pending = "pending"
    deploying = "deploying"
    success = "success"
    failed = "failed"


class TriggerSource(str, enum.Enum):
    """Pemicu deployment (dicatat di kolom ``trigger_source``)."""

    manual = "manual"
    github_webhook = "github_webhook"
    ci_token = "ci_token"


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Aplikasi yang di-deploy",
    )
    server_id: Mapped[int | None] = mapped_column(
        ForeignKey("servers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Target server (nullable — diset NULL jika server dihapus)",
    )

    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(
            DeploymentStatus,
            name="deployment_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=DeploymentStatus.pending,
        server_default=DeploymentStatus.pending.value,
        nullable=False,
    )

    branch: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Branch yang di-deploy",
    )
    trigger_source: Mapped[str] = mapped_column(
        String(20),
        default=TriggerSource.manual.value,
        server_default=TriggerSource.manual.value,
        nullable=False,
        comment="Pemicu deployment: manual | github_webhook | ci_token",
    )
    commit_sha: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="Commit SHA hasil clone (diisi setelah clone selesai)",
    )
    tag: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Git tag yang menunjuk tepat ke commit deployment, jika ada",
    )
    triggered_by: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        comment=(
            "Identitas pemicu: username, deploy-token:<nama>, atau webhook"
        ),
    )
    log_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Path file log sementara di server / lokal",
    )

    # --- Rollback metadata ---
    rollback_of: Mapped[int | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="ID deployment yang di-rollback. NULL jika bukan rollback.",
    )
    compose_path_snapshot: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment=(
            "Snapshot path compose file saat deployment ini sukses. "
            "Dipakai rollback untuk re-deploy konfigurasi lama."
        ),
    )
    is_rollback: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="True jika deployment ini adalah operasi rollback.",
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Waktu deployment dimulai",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu deployment selesai (None jika masih berjalan)",
    )
