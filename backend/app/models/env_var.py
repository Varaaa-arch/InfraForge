"""
Model SQLAlchemy untuk tabel `project_env_vars`.

Setiap baris menyimpan satu environment variable milik sebuah project.
Kolom `value` selalu disimpan dalam bentuk terenkripsi (Fernet) —
enkripsi/dekripsi dilakukan di service layer, bukan di sini.

Constraint UNIQUE (project_id, key) memastikan tidak ada key duplikat
dalam satu project, sehingga endpoint upsert bisa bekerja dengan benar.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class EnvVar(Base):
    __tablename__ = "project_env_vars"

    # Unique constraint: satu key hanya boleh ada sekali per project
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_project_env_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Nama environment variable, misal DATABASE_URL",
    )
    # Nilai disimpan terenkripsi — JANGAN tulis plaintext ke kolom ini secara langsung
    encrypted_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Nilai terenkripsi dengan Fernet; dekripsi via encryption_service",
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
