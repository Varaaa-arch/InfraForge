"""Exporter metrik Prometheus untuk container Docker."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from loguru import logger
from prometheus_client import CollectorRegistry, Gauge

from app.services import container_service

REGISTRY = CollectorRegistry()

docker_available = Gauge(
    "infraforge_docker_available",
    "1 jika Docker daemon dapat dihubungi oleh backend.",
    registry=REGISTRY,
)

container_up = Gauge(
    "infraforge_container_up",
    "1 jika container berjalan, 0 jika tidak.",
    ["name", "service", "compose_project", "image", "state"],
    registry=REGISTRY,
)

container_restart_count = Gauge(
    "infraforge_container_restart_count",
    "Jumlah restart container menurut Docker.",
    ["name", "service", "compose_project"],
    registry=REGISTRY,
)

container_cpu_percent = Gauge(
    "infraforge_container_cpu_percent",
    "Persentase pemakaian CPU container (Docker stats, per core).",
    ["name", "service", "compose_project", "image"],
    registry=REGISTRY,
)

container_memory_bytes = Gauge(
    "infraforge_container_memory_bytes",
    "Pemakaian memori container dalam byte (cache-adjusted).",
    ["name", "service", "compose_project", "image"],
    registry=REGISTRY,
)

_STATS_MAX_WORKERS = 8


def _collect_stats(
    container_ids: list[str], client: Any
) -> dict[str, container_service.ContainerStats]:
    """Ambil stats container secara paralel agar scrape tetap cepat."""
    stats_by_id: dict[str, container_service.ContainerStats] = {}
    if not container_ids:
        return stats_by_id

    with ThreadPoolExecutor(max_workers=min(_STATS_MAX_WORKERS, len(container_ids))) as pool:
        futures = {
            pool.submit(container_service.get_stats, container_id, client): container_id
            for container_id in container_ids
        }
        for future in as_completed(futures):
            container_id = futures[future]
            try:
                stats_by_id[container_id] = future.result()
            except Exception as exc:
                logger.debug(f"Metrics: stats container {container_id} gagal: {exc}")
    return stats_by_id


def collect() -> None:
    container_up.clear()
    container_restart_count.clear()
    container_cpu_percent.clear()
    container_memory_bytes.clear()
    docker_available.set(0)

    try:
        client = container_service._get_client()
        containers = client.containers.list(all=True)
    except Exception as exc:
        logger.warning(f"Metrics: Docker tidak tersedia: {exc}")
        return

    docker_available.set(1)

    running_ids = [container.id for container in containers if container.status == "running"]
    stats_by_id = _collect_stats(running_ids, client)

    for container in containers:
        labels = container.labels or {}
        attrs = container.attrs or {}
        config = attrs.get("Config") or {}
        name = container.name
        project = labels.get("com.docker.compose.project", "unknown")
        service = labels.get("com.docker.compose.service") or name
        image = config.get("Image", "")
        state = container.status or "unknown"

        container_up.labels(
            name=name,
            service=service,
            compose_project=project,
            image=image,
            state=state,
        ).set(1 if state == "running" else 0)

        container_restart_count.labels(
            name=name,
            service=service,
            compose_project=project,
        ).set(int(attrs.get("RestartCount") or 0))

        stats = stats_by_id.get(container.id)
        if stats is None:
            continue

        dimensions = {
            "name": name,
            "service": service,
            "compose_project": project,
            "image": image,
        }
        if stats.cpu_percent is not None:
            container_cpu_percent.labels(**dimensions).set(stats.cpu_percent)
        container_memory_bytes.labels(**dimensions).set(stats.memory_usage_bytes)
