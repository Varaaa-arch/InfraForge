"""
Prometheus Service — query metrik Node Exporter untuk performa server.

Berinteraksi dengan Prometheus HTTP API:
- ``GET /api/v1/query_range`` → time-series (CPU, RAM, disk, network).
- ``GET /api/v1/query``       → nilai instan (validasi target exporter).
- ``GET /api/v1/targets``     → daftar target Node Exporter yang terdaftar.

Semua fungsi memakai ``httpx.get`` sinkron seperti ``loki_service``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from loguru import logger

from app.config import settings

# Format rentang waktu: 30m, 1h, 7d, dst.
_RANGE_PATTERN = re.compile(r"^(\d+)([smhd])$")
_UNIT_SECONDS: dict[str, int] = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# Prometheus scrape interval di prometheus.yml — step diselaraskan ke kelipatan ini.
_SCRAPE_INTERVAL_SECONDS = 15
_NODE_EXPORTER_JOB = "node-exporter"


@dataclass
class MetricPoint:
    timestamp: datetime
    value: float


@dataclass
class PrometheusSeries:
    labels: dict[str, str] = field(default_factory=dict)
    points: list[MetricPoint] = field(default_factory=list)


@dataclass
class InstantSample:
    labels: dict[str, str] = field(default_factory=dict)
    value: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape_label_value(value: str) -> str:
    """Escape backslash dan double-quote agar aman di label matcher PromQL."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def instance_matcher(instance: str) -> str:
    """Bangun matcher ``instance="..."`` yang aman dari karakter khusus."""
    return f'instance="{_escape_label_value(instance)}"'


def _request(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET ke Prometheus HTTP API dan kembalikan ``data`` dari payload JSON."""
    url = f"{settings.PROMETHEUS_URL.rstrip('/')}{path}"
    try:
        response = httpx.get(url, params=params, timeout=settings.PROMETHEUS_TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(f"Request ke Prometheus gagal ({url}): {exc}")
        raise RuntimeError(f"Gagal menghubungi Prometheus: {exc}") from exc

    payload = response.json()
    if payload.get("status") != "success":
        message = payload.get("error") or "respons tidak valid"
        raise RuntimeError(f"Query Prometheus gagal: {message}")
    return payload["data"]  # type: ignore[no-any-return]


def _parse_value(raw: Any) -> float | None:
    """Parse nilai string Prometheus; abaikan NaN/Inf dan nilai tidak valid."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


# ---------------------------------------------------------------------------
# Rentang & step
# ---------------------------------------------------------------------------

def parse_range(value: str) -> int:
    """
    Konversi rentang waktu (mis. ``1h``) menjadi detik.

    Raises:
        ValueError: format tidak valid atau di luar batas 1 menit–7 hari.
    """
    match = _RANGE_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError(
            f"Format `range` tidak valid: {value!r}. Gunakan format seperti 30m, 1h, "
            "6h, 24h, atau 7d."
        )
    seconds = int(match.group(1)) * _UNIT_SECONDS[match.group(2)]
    if seconds < 60:
        raise ValueError("Rentang `range` minimal 1 menit (1m).")
    if seconds > settings.METRICS_MAX_RANGE_SECONDS:
        raise ValueError("Rentang `range` maksimum 7 hari (7d).")
    return seconds


def resolve_step(range_seconds: int, step: int | None = None) -> int:
    """
    Tentukan step query (detik) agar jumlah titik tetap wajar.

    - Tanpa ``step``: otomatis ``range / METRICS_MAX_POINTS``.
    - ``step`` terlalu kecil: dinaikkan agar titik tidak melebihi batas.
    - Hasil selalu kelipatan 15 detik (scrape interval Prometheus).
    """
    max_points = max(settings.METRICS_MAX_POINTS, 2)
    minimal_step = math.ceil(range_seconds / max_points)
    effective = minimal_step if step is None else max(step, minimal_step)
    effective = max(effective, _SCRAPE_INTERVAL_SECONDS)
    snapped = math.ceil(effective / _SCRAPE_INTERVAL_SECONDS) * _SCRAPE_INTERVAL_SECONDS
    return int(snapped)


# ---------------------------------------------------------------------------
# Query Prometheus
# ---------------------------------------------------------------------------

def query_range(
    promql: str, start: float, end: float, step: int
) -> list[PrometheusSeries]:
    """Jalankan ``query_range`` dan kembalikan daftar seri beserta titiknya."""
    data = _request(
        "/api/v1/query_range",
        {
            "query": promql,
            "start": f"{start:.3f}",
            "end": f"{end:.3f}",
            "step": str(step),
        },
    )

    series: list[PrometheusSeries] = []
    for item in data.get("result") or []:
        labels = {
            key: value
            for key, value in (item.get("metric") or {}).items()
            if key != "__name__"
        }
        points: list[MetricPoint] = []
        for timestamp, raw_value in item.get("values") or []:
            value = _parse_value(raw_value)
            if value is None:
                continue
            points.append(
                MetricPoint(
                    timestamp=datetime.fromtimestamp(float(timestamp), tz=UTC),
                    value=value,
                )
            )
        series.append(PrometheusSeries(labels=labels, points=points))
    return series


def query_instant(promql: str) -> float | None:
    """Jalankan ``query`` instan dan kembalikan nilai pertama (atau None)."""
    data = _request("/api/v1/query", {"query": promql})
    result = data.get("result") or []
    if not result:
        return None
    value_pair = result[0].get("value") or [None, None]
    return _parse_value(value_pair[1])


def query_instant_samples(promql: str) -> list[InstantSample]:
    """Jalankan ``query`` instan dan kembalikan semua sampel beserta labelnya."""
    data = _request("/api/v1/query", {"query": promql})

    samples: list[InstantSample] = []
    for item in data.get("result") or []:
        value_pair = item.get("value") or [None, None]
        value = _parse_value(value_pair[1])
        if value is None:
            continue
        labels = {
            key: label_value
            for key, label_value in (item.get("metric") or {}).items()
            if key != "__name__"
        }
        samples.append(InstantSample(labels=labels, value=value))
    return samples


def list_node_exporter_targets() -> list[str]:
    """Daftar label ``instance`` untuk target aktif dengan job Node Exporter."""
    data = _request("/api/v1/targets", {})
    instances: set[str] = set()
    for target in data.get("activeTargets") or []:
        labels = target.get("labels") or {}
        if labels.get("job") != _NODE_EXPORTER_JOB:
            continue
        instance = labels.get("instance")
        if instance:
            instances.add(str(instance))
    return sorted(instances)


# ---------------------------------------------------------------------------
# Query builders (Node Exporter)
# ---------------------------------------------------------------------------

def build_cpu_query(instance: str) -> str:
    """Persentase pemakaian CPU host (0–100)."""
    matcher = instance_matcher(instance)
    return (
        "100 - (avg by (instance) (rate(node_cpu_seconds_total"
        f'{{mode="idle", {matcher}}}[5m])) * 100)'
    )


def build_memory_query(instance: str) -> str:
    """Persentase pemakaian RAM host (0–100)."""
    matcher = instance_matcher(instance)
    return (
        f"(1 - (node_memory_MemAvailable_bytes{{{matcher}}}"
        f" / node_memory_MemTotal_bytes{{{matcher}}})) * 100"
    )


def build_disk_usage_query(instance: str) -> str:
    """Persentase pemakaian filesystem root (0–100)."""
    matcher = instance_matcher(instance)
    filesystem = 'mountpoint="/",fstype!~"tmpfs|overlay|squashfs|ramfs|fuse.lxcfs"'
    return (
        f"(1 - (node_filesystem_avail_bytes{{{matcher},{filesystem}}}"
        f" / node_filesystem_size_bytes{{{matcher},{filesystem}}})) * 100"
    )


def build_disk_io_query(instance: str) -> str:
    """Persentase waktu disk sibuk (0–100) hasil agregasi semua device."""
    matcher = instance_matcher(instance)
    return (
        "sum by (instance) (rate(node_disk_io_time_seconds_total"
        f"{{{matcher}}}[5m])) * 100"
    )


def build_network_rx_query(instance: str) -> str:
    """Throughput network masuk (byte/detik), tanpa interface loopback."""
    matcher = instance_matcher(instance)
    return (
        "sum by (instance) (rate(node_network_receive_bytes_total"
        f'{{{matcher},device!="lo"}}[5m]))'
    )


def build_network_tx_query(instance: str) -> str:
    """Throughput network keluar (byte/detik), tanpa interface loopback."""
    matcher = instance_matcher(instance)
    return (
        "sum by (instance) (rate(node_network_transmit_bytes_total"
        f'{{{matcher},device!="lo"}}[5m]))'
    )


# ---------------------------------------------------------------------------
# Query builders (container trends — exporter backend)
# ---------------------------------------------------------------------------

_CONTAINER_CPU_METRIC = "infraforge_container_cpu_percent"
_CONTAINER_MEMORY_METRIC = "infraforge_container_memory_bytes"
_CONTAINER_MEMORY_LIMIT_METRIC = "infraforge_container_memory_limit_bytes"


def _container_matcher(name: str) -> str:
    return f'name="{_escape_label_value(name)}"'


def build_top_containers_cpu_query(limit: int, window: str = "5m") -> str:
    """Top container berdasarkan rata-rata pemakaian CPU, hanya yang running."""
    return (
        f"topk({limit}, "
        f"avg_over_time({_CONTAINER_CPU_METRIC}{{name!=\"\"}}[{window}])"
        f' and on(name) (infraforge_container_up{{name!=""}} == 1))'
    )


def build_container_cpu_range_query(name: str) -> str:
    """Time-series CPU satu container (untuk sparkline tren)."""
    return f"{_CONTAINER_CPU_METRIC}{{{_container_matcher(name)}}}"


def build_container_memory_query(name: str) -> str:
    """Nilai RAM instan satu container."""
    return f"{_CONTAINER_MEMORY_METRIC}{{{_container_matcher(name)}}}"


def build_container_cpu_all_query() -> str:
    """Nilai CPU instan seluruh container (dari exporter backend)."""
    return f'{_CONTAINER_CPU_METRIC}{{name!=""}}'


def build_container_memory_all_query() -> str:
    """Nilai RAM instan seluruh container (dari exporter backend)."""
    return f'{_CONTAINER_MEMORY_METRIC}{{name!=""}}'


def build_container_memory_limit_all_query() -> str:
    """Limit RAM seluruh container (dari exporter backend)."""
    return f'{_CONTAINER_MEMORY_LIMIT_METRIC}{{name!=""}}'


def list_node_exporter_up() -> dict[str, float]:
    """
    Status ``up`` tiap target node-exporter.

    Returns:
        Mapping ``instance → nilai up`` (1 = hidup, 0 = down).
        Instance yang tidak terdaftar tidak muncul di mapping.
    """
    samples = query_instant_samples(f'up{{job="{_NODE_EXPORTER_JOB}"}}')
    result: dict[str, float] = {}
    for sample in samples:
        instance = sample.labels.get("instance")
        if instance:
            result[instance] = sample.value
    return result
