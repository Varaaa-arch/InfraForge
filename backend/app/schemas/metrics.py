"""Schema Pydantic untuk metrik server (Prometheus) dan container (Docker SDK)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    """Satu titik time-series."""

    timestamp: datetime
    value: float


class MetricSummary(BaseModel):
    """Ringkasan nilai sebuah seri: current, rata-rata, maksimum, minimum."""

    current: float
    average: float
    maximum: float
    minimum: float


class MetricSeries(BaseModel):
    """Time-series satu metrik beserta ringkasannya."""

    unit: str
    points: list[MetricPoint] = Field(default_factory=list)
    summary: MetricSummary | None = None


class ServerMetricsResponse(BaseModel):
    """Respons GET /servers/{id}/metrics."""

    server_id: int
    server_name: str
    exporter_instance: str | None
    range: str
    step_seconds: int
    available: bool
    message: str | None = None
    generated_at: datetime
    series: dict[str, MetricSeries] = Field(default_factory=dict)


class ContainerMemoryStats(BaseModel):
    """Pemakaian memori container."""

    usage_bytes: int
    limit_bytes: int
    percent: float | None


class ContainerNetworkStats(BaseModel):
    """Total byte network container sejak container dimulai."""

    rx_bytes: int
    tx_bytes: int


class ContainerBlockIOStats(BaseModel):
    """Total byte baca/tulis block device container."""

    read_bytes: int
    write_bytes: int


class ContainerTrend(BaseModel):
    """Satu container pada panel tren (CPU/RAM dari exporter backend)."""

    name: str
    service: str | None = None
    compose_project: str | None = None
    image: str | None = None
    cpu_percent: float
    memory_bytes: int
    cpu_points: list[MetricPoint] = Field(default_factory=list)


class ContainerTrendsResponse(BaseModel):
    """Respons GET /containers/usage/top."""

    range: str
    step_seconds: int
    available: bool
    message: str | None = None
    generated_at: datetime
    containers: list[ContainerTrend] = Field(default_factory=list)


class ContainerMetricsResponse(BaseModel):
    """Respons GET /containers/{id}/metrics."""

    container_id: str
    name: str
    image: str
    status: str
    cpu_percent: float | None
    cpu_count: int | None
    memory: ContainerMemoryStats
    network: ContainerNetworkStats
    blkio: ContainerBlockIOStats
    pids_current: int | None
    sampled_at: datetime
