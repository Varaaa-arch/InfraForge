"""Skema request/response untuk target TLS/SSL."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.tls_domain import TlsDomainStatus


class TlsDomainCreate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    host: str = Field(
        min_length=1,
        max_length=253,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$|^[A-Za-z0-9]$",
    )
    port: int = Field(default=443, ge=1, le=65535)
    enabled: bool = True
    warning_days: int = Field(default=30, ge=1, le=365)
    check_now: bool = True

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class TlsDomainUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    host: str | None = Field(
        default=None,
        min_length=1,
        max_length=253,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$|^[A-Za-z0-9]$",
    )
    port: int | None = Field(default=None, ge=1, le=65535)
    enabled: bool | None = None
    warning_days: int | None = Field(default=None, ge=1, le=365)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class TlsDomainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    host: str
    port: int
    enabled: bool
    warning_days: int
    status: TlsDomainStatus
    days_remaining: int | None
    expiry_date: datetime | None
    issuer: str | None
    subject: str | None
    protocol: str | None
    trusted: bool
    error_message: str | None
    last_checked_at: datetime | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class TlsDomainListResponse(BaseModel):
    items: list[TlsDomainResponse]
    total: int


class TlsDomainCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tls_domain_id: int
    checked_at: datetime
    status: str
    days_remaining: int | None
    expiry_date: datetime | None
    issuer: str | None
    subject: str | None
    protocol: str | None
    trusted: bool
    error_message: str | None
    alert_sent: bool


class TlsDomainDetailResponse(TlsDomainResponse):
    checks: list[TlsDomainCheckResponse]
