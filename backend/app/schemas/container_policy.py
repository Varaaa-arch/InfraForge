"""Schema untuk policy resource dan auto-healing container."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RestartPolicyLiteral = Literal["no", "always", "unless-stopped", "on-failure"]

CPU_PERIOD_DEFAULT = 100_000


class ContainerPolicyUpsert(BaseModel):
    """Payload untuk membuat/mengubah policy sebuah container."""

    cpu_limit_cores: float | None = Field(default=None, gt=0, le=64)
    cpu_quota: int | None = Field(default=None, ge=0, le=64_000_000)
    cpu_period: int | None = Field(default=None, ge=1_000, le=1_000_000)
    memory_limit_mib: int | None = Field(default=None, ge=0, le=1_048_576)
    restart_policy: RestartPolicyLiteral = "no"
    auto_heal_enabled: bool = False
    unhealthy_threshold: int = Field(default=3, ge=1, le=60)
    max_restarts: int = Field(default=3, ge=0, le=100)
    restart_cooldown_seconds: int = Field(default=300, ge=0, le=86_400)
    apply_now: bool = True

    @model_validator(mode="after")
    def normalize_limits(self) -> ContainerPolicyUpsert:
        period = self.cpu_period or CPU_PERIOD_DEFAULT
        self.cpu_period = period

        if self.cpu_quota is not None:
            quota = self.cpu_quota or None
            self.cpu_quota = quota
            self.cpu_limit_cores = (
                round(quota / period, 3) if quota is not None else None
            )
        elif self.cpu_limit_cores is not None:
            self.cpu_quota = int(round(self.cpu_limit_cores * period))
        return self


class EffectiveContainerLimits(BaseModel):
    """Nilai limit yang sedang aktif di Docker (HostConfig)."""

    cpu_limit_cores: float | None = None
    cpu_quota: int | None = None
    cpu_period: int | None = None
    memory_limit_bytes: int | None = None
    restart_policy: str = "no"


class ContainerPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    container_name: str
    container_id: str | None
    compose_project: str | None
    compose_service: str | None
    cpu_limit_cores: float | None
    cpu_quota: int | None
    cpu_period: int
    memory_limit_bytes: int | None
    restart_policy: str
    auto_heal_enabled: bool
    unhealthy_threshold: int
    max_restarts: int
    restart_cooldown_seconds: int
    unhealthy_streak: int
    last_health_status: str | None
    last_restart_at: datetime | None
    restart_count_window: int
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ContainerPolicyDetail(BaseModel):
    container_id: str
    container_name: str
    compose_project: str | None = None
    compose_service: str | None = None
    status: str
    health: str | None = None
    policy: ContainerPolicyResponse | None = None
    effective: EffectiveContainerLimits


class ContainerPolicyMutationResult(BaseModel):
    policy: ContainerPolicyResponse
    effective: EffectiveContainerLimits
    message: str
