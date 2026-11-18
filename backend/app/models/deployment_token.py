"""Model deployment token (CI/CD trigger) per project.

Format token: ``dt_<prefix>_<secret>``.
- ``prefix`` (8 hex char) disimpan untuk ditampilkan di UI.
- Hanya **hash SHA-256** dari token lengkap yang disimpan di database.
- Token plaintext hanya dikembalikan sekali saat dibuat.
- Token terikat ke satu project dan dipakai endpoint publik
  ``POST /deploy/trigger/{token}`` untuk memicu deployment dari CI/CD.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class DeploymentToken(Base):
    __tablename__ = "deployment_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Project yang boleh di-deploy dengan token ini",
    )
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL = token project-wide; terisi = token hanya untuk aplikasi ini",
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User yang membuat token (NULL jika user dihapus)",
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and self.expires_at <= now
