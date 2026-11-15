"""Schema API token (Personal Access Token)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ApiTokenScope = Literal["read", "write"]


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[ApiTokenScope] | None = Field(
        default=None,
        description=(
            "Daftar scope token: `read` (GET saja) dan/atau `write`. "
            "Kosong/null berarti akses penuh sesuai peran user."
        ),
    )
    expires_in_days: int | None = Field(
        default=None, ge=1, le=365, description="Masa berlaku token dalam hari"
    )


class ApiTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    scopes: list[str] | None
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiTokenCreated(ApiTokenResponse):
    token: str
