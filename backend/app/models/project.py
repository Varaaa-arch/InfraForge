import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class Visibility(str, enum.Enum):
    private = "private"
    public = "public"


class GitProvider(str, enum.Enum):
    github = "github"
    gitlab = "gitlab"
    bitbucket = "bitbucket"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, name="project_visibility", values_callable=lambda e: [m.value for m in e]),
        default=Visibility.private,
        server_default=Visibility.private.value,
        nullable=False,
    )
    repository_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider: Mapped[GitProvider | None] = mapped_column(
        Enum(GitProvider, name="git_provider", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    repository_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
