"""Exporter metrik Prometheus untuk container Docker."""

from __future__ import annotations

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


def collect() -> None:
    container_up.clear()
    container_restart_count.clear()
    docker_available.set(0)

    try:
        client = container_service._get_client()
        containers = client.containers.list(all=True)
    except Exception as exc:
        logger.warning(f"Metrics: Docker tidak tersedia: {exc}")
        return

    docker_available.set(1)
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
