import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class AuthType(str, enum.Enum):
    password = "password"
    private_key = "private_key"


class ServerStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    error = "error"


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    host: Mapped[str] = mapped_column(String(253), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=22, server_default="22", nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    auth_type: Mapped[AuthType] = mapped_column(
        Enum(AuthType, name="server_auth_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    # Sensitif — di production sebaiknya dienkripsi at-rest
    private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ServerStatus] = mapped_column(
        Enum(ServerStatus, name="server_status", values_callable=lambda e: [m.value for m in e]),
        default=ServerStatus.inactive,
        server_default=ServerStatus.inactive.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
