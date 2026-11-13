"""
Server Metrics Service — agregasi metrik Node Exporter per server.

Alur:
1. Validasi server punya ``exporter_instance``.
2. Pastikan target exporter terdaftar & up di Prometheus.
3. Jalankan query range untuk CPU, RAM, disk usage, disk I/O, dan network.
4. Kembalikan time-series + ringkasan (current/avg/max/min).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

from app.models.server import Server
from app.schemas.metrics import (
    MetricPoint,
    MetricSeries,
    MetricSummary,
    ServerMetricsResponse,
)
from app.services import prometheus_service

SeriesBuilder = Callable[[str], str]

_SERIES_DEFINITIONS: list[tuple[str, str, SeriesBuilder]] = [
    ("cpu_percent", "%", prometheus_service.build_cpu_query),
    ("memory_percent", "%", prometheus_service.build_memory_query),
    ("disk_usage_percent", "%", prometheus_service.build_disk_usage_query),
    ("disk_io_percent", "%", prometheus_service.build_disk_io_query),
    ("network_rx_bytes", "bytes/s", prometheus_service.build_network_rx_query),
    ("network_tx_bytes", "bytes/s", prometheus_service.build_network_tx_query),
]


def _summarize(points: list[MetricPoint]) -> MetricSummary | None:
    if not points:
        return None
    values = [point.value for point in points]
    return MetricSummary(
        current=round(values[-1], 2),
        average=round(sum(values) / len(values), 2),
        maximum=round(max(values), 2),
        minimum=round(min(values), 2),
    )


def collect(
    server: Server, range_value: str, step: int | None = None
) -> ServerMetricsResponse:
    """
    Kumpulkan metrik server dari Prometheus.

    Raises:
        ValueError: format ``range`` tidak valid.
        RuntimeError: Prometheus tidak dapat dihubungi / query gagal.
    """
    range_seconds = prometheus_service.parse_range(range_value)
    step_seconds = prometheus_service.resolve_step(range_seconds, step)
    generated_at = datetime.now(tz=UTC)

    if not server.exporter_instance:
        return ServerMetricsResponse(
            server_id=server.id,
            server_name=server.name,
            exporter_instance=None,
            range=range_value,
            step_seconds=step_seconds,
            available=False,
            message="Server ini belum dikonfigurasi dengan exporter Prometheus.",
            generated_at=generated_at,
            series={},
        )

    matcher = prometheus_service.instance_matcher(server.exporter_instance)
    up_value = prometheus_service.query_instant(f"up{{{matcher}}}")

    if up_value is None:
        return ServerMetricsResponse(
            server_id=server.id,
            server_name=server.name,
            exporter_instance=server.exporter_instance,
            range=range_value,
            step_seconds=step_seconds,
            available=False,
            message=(
                f"Exporter '{server.exporter_instance}' belum terdaftar di Prometheus."
            ),
            generated_at=generated_at,
            series={},
        )

    if up_value != 1:
        return ServerMetricsResponse(
            server_id=server.id,
            server_name=server.name,
            exporter_instance=server.exporter_instance,
            range=range_value,
            step_seconds=step_seconds,
            available=False,
            message=f"Exporter '{server.exporter_instance}' sedang down.",
            generated_at=generated_at,
            series={},
        )

    end = time.time()
    start = end - range_seconds

    series_map: dict[str, MetricSeries] = {}
    for name, unit, builder in _SERIES_DEFINITIONS:
        raw_series = prometheus_service.query_range(
            builder(server.exporter_instance), start, end, step_seconds
        )
        points = [
            MetricPoint(timestamp=point.timestamp, value=point.value)
            for point in (raw_series[0].points if raw_series else [])
        ]
        series_map[name] = MetricSeries(
            unit=unit,
            points=points,
            summary=_summarize(points),
        )

    return ServerMetricsResponse(
        server_id=server.id,
        server_name=server.name,
        exporter_instance=server.exporter_instance,
        range=range_value,
        step_seconds=step_seconds,
        available=True,
        message=None,
        generated_at=generated_at,
        series=series_map,
    )
