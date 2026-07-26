from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.project import GitProvider, Visibility


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Visibility = Visibility.private


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Visibility | None = None


class RepositoryUpdate(BaseModel):
    repository_url: str = Field(min_length=1, max_length=500)
    default_branch: str = Field(default="main", min_length=1, max_length=100)
    provider: GitProvider

    @field_validator("repository_url")
    @classmethod
    def validate_repository_url(cls, value: str) -> str:
        if not (value.startswith("https://") or value.startswith("http://")):
            raise ValueError("repository_url harus URL valid (diawali http:// atau https://)")
        return value


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    slug: str
    description: str | None
    visibility: Visibility
    repository_url: str | None
    default_branch: str | None
    provider: GitProvider | None
    repository_connected_at: datetime | None
    created_at: datetime
    updated_at: datetime
