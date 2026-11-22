"""Schema API pemindaian kerentanan image container."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

IMAGE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/:@-]*$"


class ImageScanTrigger(BaseModel):
    image_name: str = Field(
        min_length=1,
        max_length=500,
        pattern=IMAGE_NAME_PATTERN,
        description="Referensi image, mis. nginx:1.27 atau ghcr.io/org/app@sha256:...",
    )
    project_id: int | None = Field(default=None, ge=1)


class VulnerabilityFinding(BaseModel):
    cve_id: str
    package: str
    installed_version: str | None = None
    fixed_version: str | None = None
    severity: str = "unknown"
    title: str | None = None
    target: str | None = None
    primary_url: str | None = None


class ImageScanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    image_name: str
    image_digest: str | None
    status: str
    overall_severity: str | None
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    total_count: int
    scanner: str
    error_message: str | None
    requested_by: str | None
    scanned_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ImageScanDetail(ImageScanSummary):
    findings: list[VulnerabilityFinding] = Field(default_factory=list)

    @field_validator("findings", mode="before")
    @classmethod
    def findings_none_to_list(cls, value: object) -> object:
        return value or []


class ImageScanListResponse(BaseModel):
    items: list[ImageScanSummary]
    total: int
    limit: int
    offset: int
