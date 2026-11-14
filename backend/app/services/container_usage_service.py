"""
Container Usage Service — pemakaian CPU/RAM per container dari Prometheus.

Sumber data adalah gauge exporter backend yang di-scrape Prometheus setiap 15
detik:
- ``infraforge_container_cpu_percent``
- ``infraforge_container_memory_bytes``
- ``infraforge_container_memory_limit_bytes``

Jika Prometheus tidak dapat dihubungi, fungsi ``collect_usage`` mengembalikan
mapping kosong — pemanggil tetap bisa menampilkan daftar container tanpa usage.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from app.services import prometheus_service


@dataclass(frozen=True)
class ContainerUsage:
    """Usage resource satu container."""

    cpu_percent: float | None = None
    memory_usage_bytes: int | None = None
    memory_limit_bytes: int | None = None

    @property
    def memory_percent(self) -> float | None:
        """Persentase memori terpakai, atau None bila limit/usage tidak tersedia."""
        if self.memory_usage_bytes is None or not self.memory_limit_bytes:
            return None
        return round(self.memory_usage_bytes / self.memory_limit_bytes * 100, 2)


def _samples_by_name(promql: str) -> dict[str, float]:
    samples = prometheus_service.query_instant_samples(promql)
    return {
        sample.labels["name"]: sample.value
        for sample in samples
        if sample.labels.get("name")
    }


def collect_usage() -> dict[str, ContainerUsage]:
    """
    Kumpulkan usage CPU/RAM semua container.

    Returns:
        Mapping nama container → usage. Kosong bila Prometheus tidak tersedia.
    """
    try:
        cpu_by_name = _samples_by_name(
            prometheus_service.build_container_cpu_all_query()
        )
        memory_by_name = _samples_by_name(
            prometheus_service.build_container_memory_all_query()
        )
        limit_by_name = _samples_by_name(
            prometheus_service.build_container_memory_limit_all_query()
        )
    except RuntimeError as exc:
        logger.warning(f"Usage container: Prometheus tidak dapat dihubungi: {exc}")
        return {}

    usage: dict[str, ContainerUsage] = {}
    for name in set(cpu_by_name) | set(memory_by_name) | set(limit_by_name):
        usage[name] = ContainerUsage(
            cpu_percent=round(cpu_by_name[name], 2) if name in cpu_by_name else None,
            memory_usage_bytes=(
                int(memory_by_name[name]) if name in memory_by_name else None
            ),
            memory_limit_bytes=(
                int(limit_by_name[name]) if name in limit_by_name else None
            ),
        )
    return usage
