"""
Container Trends Service — top container berdasarkan CPU/RAM dari Prometheus.

Metrik berasal dari exporter backend (``job=backend``):
``infraforge_container_cpu_percent`` dan ``infraforge_container_memory_bytes``.
Data ini di-scrape Prometheus sehingga tren historis bisa di-query dengan
``avg_over_time`` dan ``query_range``.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from loguru import logger

from app.schemas.metrics import (
    ContainerTrend,
    ContainerTrendsResponse,
    MetricPoint,
)
from app.services import prometheus_service

_TREND_WINDOW = "5m"
_MAX_LIMIT = 20


def collect(range_value: str = "1h", limit: int = 5) -> ContainerTrendsResponse:
    """
    Kumpulkan top container + tren CPU historis.

    Raises:
        ValueError: format ``range`` tidak valid.
        RuntimeError: Prometheus tidak dapat dihubungi / query gagal.
    """
    range_seconds = prometheus_service.parse_range(range_value)
    step_seconds = prometheus_service.resolve_step(range_seconds)
    generated_at = datetime.now(tz=UTC)
    limit = max(1, min(limit, _MAX_LIMIT))

    top_samples = prometheus_service.query_instant_samples(
        prometheus_service.build_top_containers_cpu_query(limit, _TREND_WINDOW)
    )

    end = time.time()
    start = end - range_seconds
    containers: list[ContainerTrend] = []

    for sample in top_samples:
        name = sample.labels.get("name")
        if not name:
            continue

        try:
            memory_samples = prometheus_service.query_instant_samples(
                prometheus_service.build_container_memory_query(name)
            )
            raw_series = prometheus_service.query_range(
                prometheus_service.build_container_cpu_range_query(name),
                start,
                end,
                step_seconds,
            )
        except RuntimeError as exc:
            logger.warning(f"Gagal mengambil tren container '{name}': {exc}")
            continue

        memory_bytes = (
            int(round(memory_samples[0].value)) if memory_samples else 0
        )
        points = [
            MetricPoint(timestamp=point.timestamp, value=point.value)
            for point in (raw_series[0].points if raw_series else [])
        ]

        containers.append(
            ContainerTrend(
                name=name,
                service=sample.labels.get("service"),
                compose_project=sample.labels.get("compose_project"),
                image=sample.labels.get("image"),
                cpu_percent=round(sample.value, 2),
                memory_bytes=memory_bytes,
                cpu_points=points,
            )
        )

    return ContainerTrendsResponse(
        range=range_value,
        step_seconds=step_seconds,
        available=True,
        message=(
            None
            if containers
            else "Belum ada data metrik container dari exporter backend."
        ),
        generated_at=generated_at,
        containers=containers,
    )
