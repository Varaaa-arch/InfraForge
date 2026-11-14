"""Test exporter metrik container (infraforge_container_*)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from prometheus_client import generate_latest

from app.services import container_service, metrics_service


class FakeContainer:
    def __init__(
        self,
        container_id: str,
        name: str,
        status: str = "running",
        image: str = "nginx:latest",
    ) -> None:
        self.id = container_id
        self.name = name
        self.status = status
        self.labels = {
            "com.docker.compose.project": "infraforge",
            "com.docker.compose.service": name,
        }
        self.attrs = {"Config": {"Image": image}, "RestartCount": 1}


class FakeContainers:
    def __init__(self, items: list[FakeContainer]) -> None:
        self._items = items

    def list(self, all: bool = True) -> list[FakeContainer]:
        return self._items


class FakeClient:
    def __init__(self, items: list[FakeContainer]) -> None:
        self.containers = FakeContainers(items)


def _stats(container_id: str) -> container_service.ContainerStats:
    return container_service.ContainerStats(
        id=container_id,
        name="web",
        image="nginx:latest",
        status="running",
        cpu_percent=0.7,
        cpu_count=8,
        memory_usage_bytes=104857600,
        memory_limit_bytes=1073741824,
        memory_percent=9.77,
        network_rx_bytes=1,
        network_tx_bytes=2,
        blkio_read_bytes=3,
        blkio_write_bytes=4,
        pids_current=5,
        sampled_at=datetime.now(tz=UTC),
    )


def _exposition() -> str:
    return generate_latest(metrics_service.REGISTRY).decode()


def _metric_lines(name: str) -> list[str]:
    return [
        line for line in _exposition().splitlines() if line.startswith(f"{name}{{")
    ]


def test_collect_sets_cpu_and_memory_gauges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient([FakeContainer("c1", "web")])
    monkeypatch.setattr(container_service, "_get_client", lambda: client)
    monkeypatch.setattr(
        container_service,
        "get_stats",
        lambda container_id, client=None: _stats(container_id),
    )

    metrics_service.collect()

    cpu_lines = _metric_lines("infraforge_container_cpu_percent")
    memory_lines = _metric_lines("infraforge_container_memory_bytes")

    assert len(cpu_lines) == 1
    assert 'name="web"' in cpu_lines[0]
    assert cpu_lines[0].endswith(" 0.7")
    assert len(memory_lines) == 1
    assert memory_lines[0].endswith(" 1.048576e+08")
    assert "infraforge_docker_available 1.0" in _exposition()


def test_collect_skips_stats_for_stopped_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient(
        [
            FakeContainer("c1", "web", status="running"),
            FakeContainer("c2", "old", status="exited"),
        ]
    )
    monkeypatch.setattr(container_service, "_get_client", lambda: client)
    monkeypatch.setattr(
        container_service,
        "get_stats",
        lambda container_id, client=None: _stats(container_id),
    )

    metrics_service.collect()

    assert len(_metric_lines("infraforge_container_cpu_percent")) == 1
    up_lines = _metric_lines("infraforge_container_up")
    assert len(up_lines) == 2
    assert any('name="old"' in line and line.endswith(" 0.0") for line in up_lines)


def test_collect_handles_docker_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail() -> Any:
        raise RuntimeError("Tidak dapat terhubung ke Docker daemon")

    monkeypatch.setattr(container_service, "_get_client", _fail)

    metrics_service.collect()

    assert "infraforge_docker_available 0.0" in _exposition()
    assert _metric_lines("infraforge_container_cpu_percent") == []


def test_collect_publishes_zero_cpu_when_no_usage_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient([FakeContainer("c1", "web")])
    monkeypatch.setattr(container_service, "_get_client", lambda: client)

    def _stats_without_cpu(container_id: str) -> container_service.ContainerStats:
        stats = _stats(container_id)
        stats.cpu_percent = None
        return stats

    monkeypatch.setattr(
        container_service,
        "get_stats",
        lambda container_id, client=None: _stats_without_cpu(container_id),
    )

    metrics_service.collect()

    cpu_lines = _metric_lines("infraforge_container_cpu_percent")
    assert len(cpu_lines) == 1
    assert cpu_lines[0].endswith(" 0.0")


def test_collect_exports_memory_limit_gauge(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient([FakeContainer("c1", "web")])
    monkeypatch.setattr(container_service, "_get_client", lambda: client)
    monkeypatch.setattr(
        container_service,
        "get_stats",
        lambda container_id, client=None: _stats(container_id),
    )

    metrics_service.collect()

    limit_lines = _metric_lines("infraforge_container_memory_limit_bytes")
    assert len(limit_lines) == 1
    assert limit_lines[0].endswith(" 1.073741824e+09")


def test_collect_tolerates_stats_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient([FakeContainer("c1", "web")])
    monkeypatch.setattr(container_service, "_get_client", lambda: client)

    def _fail(_container_id: str, client: Any = None) -> Any:
        raise RuntimeError("stats gagal")

    monkeypatch.setattr(container_service, "get_stats", _fail)

    metrics_service.collect()

    assert _metric_lines("infraforge_container_cpu_percent") == []
    assert len(_metric_lines("infraforge_container_up")) == 1
