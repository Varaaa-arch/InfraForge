from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.models.project import Visibility


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=20000)
    visibility: Visibility = Visibility.private


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=20000)
    visibility: Visibility | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    slug: str
    description: str | None
    visibility: Visibility
    created_at: datetime
    updated_at: datetime
