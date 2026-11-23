"""Skema ringkasan posture keamanan platform."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PostureCategory = Literal["image", "tls", "container"]
PostureCheckStatus = Literal["pass", "warn", "fail", "unknown"]
PostureSeverity = Literal["critical", "high", "warning", "info"]
PostureLevel = Literal["aman", "perlu_perhatian", "berisiko"]


class ImagePostureSummary(BaseModel):
    total_scans: int
    completed: int
    failed: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    affected_images: int
    latest_scanned_at: datetime | None = None


class TlsPostureSummary(BaseModel):
    total: int
    enabled: int
    healthy: int
    expiring: int
    expired: int
    invalid: int
    error: int
    pending: int


class ContainerPostureSummary(BaseModel):
    available: bool
    total: int
    running: int
    privileged: int
    root_user: int
    writable_rootfs: int
    missing_cap_drop_all: int
    missing_no_new_privileges: int
    error_message: str | None = None


class PostureCheck(BaseModel):
    key: str
    category: PostureCategory
    title: str
    status: PostureCheckStatus
    severity: PostureSeverity
    detail: str
    count: int = 0


class PostureFinding(BaseModel):
    category: PostureCategory
    severity: PostureSeverity
    title: str
    detail: str
    resource: str | None = None


class SecurityPostureSummary(BaseModel):
    score: int = Field(ge=0, le=100)
    level: PostureLevel
    generated_at: datetime
    images: ImagePostureSummary
    tls: TlsPostureSummary
    containers: ContainerPostureSummary
    checks: list[PostureCheck]
    findings: list[PostureFinding]
