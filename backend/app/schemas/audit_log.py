"""Schema API audit log."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    username: str | None
    action: str
    method: str
    path: str
    resource_type: str | None
    resource_id: str | None
    status_code: int
    ip_address: str | None
    user_agent: str | None
    details: dict[str, Any] | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


class AuditLogFilterMeta(BaseModel):
    actions: list[str]
    usernames: list[str]
    is_admin: bool
