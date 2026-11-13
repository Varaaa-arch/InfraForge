"""Test untuk GET /containers/{id}/metrics dan container_service.get_stats."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services import container_service
from app.services.container_service import ContainerStats


def _unique_user() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "password123",
    }


def _register_and_login(client: TestClient, payload: dict[str, str]) -> dict[str, str]:
    client.post("/auth/register", json=payload)
    login_response = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    return dict(login_response.json()["data"])


def _auth_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _make_container(raw_stats: object) -> MagicMock:
    container = MagicMock()
    container.short_id = "abc123def456"
    container.name = "web_1"
    container.status = "running"
    container.image.tags = ["nginx:latest"]
    container.image.short_id = "imgshort"
    container.stats.return_value = raw_stats
    return container


def _raw_stats() -> dict[str, object]:
    return {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 1_100_000_000},
            "system_cpu_usage": 19_000_000_000,
            "online_cpus": 4,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 1_000_000_000},
            "system_cpu_usage": 18_000_000_000,
        },
        "memory_stats": {
            "usage": 300_000_000,
            "limit": 1_000_000_000,
            "stats": {"inactive_file": 100_000_000},
        },
        "networks": {
            "eth0": {"rx_bytes": 1000, "tx_bytes": 2000},
            "eth1": {"rx_bytes": 500, "tx_bytes": 100},
        },
        "blkio_stats": {
            "io_service_bytes_recursive": [
                {"op": "read", "value": 4096},
                {"op": "write", "value": 8192},
                {"op": "sync", "value": 999},
            ]
        },
        "pids_stats": {"current": 12},
    }


def _sample_stats() -> ContainerStats:
    return ContainerStats(
        id="abc123def456",
        name="web_1",
        image="nginx:latest",
        status="running",
        cpu_percent=40.0,
        cpu_count=4,
        memory_usage_bytes=200_000_000,
        memory_limit_bytes=1_000_000_000,
        memory_percent=20.0,
        network_rx_bytes=1500,
        network_tx_bytes=2100,
        blkio_read_bytes=4096,
        blkio_write_bytes=8192,
        pids_current=12,
        sampled_at=datetime.now(tz=UTC),
    )


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_computes_cpu_memory_network_and_blkio(self) -> None:
        container = _make_container(_raw_stats())
        with (
            patch("app.services.container_service._get_client"),
            patch(
                "app.services.container_service._get_container",
                return_value=container,
            ),
        ):
            stats = container_service.get_stats("abc123def456")

        assert stats.cpu_percent == 40.0
        assert stats.cpu_count == 4
        assert stats.memory_usage_bytes == 200_000_000
        assert stats.memory_percent == 20.0
        assert stats.network_rx_bytes == 1500
        assert stats.network_tx_bytes == 2100
        assert stats.blkio_read_bytes == 4096
        assert stats.blkio_write_bytes == 8192
        assert stats.pids_current == 12
        assert stats.image == "nginx:latest"

    def test_cpu_percent_none_without_precpu_samples(self) -> None:
        raw = _raw_stats()
        raw["precpu_stats"] = {}
        container = _make_container(raw)
        with (
            patch("app.services.container_service._get_client"),
            patch(
                "app.services.container_service._get_container",
                return_value=container,
            ),
        ):
            stats = container_service.get_stats("abc123def456")

        assert stats.cpu_percent is None

    def test_memory_percent_none_when_limit_zero(self) -> None:
        raw = _raw_stats()
        raw["memory_stats"] = {"usage": 100, "limit": 0, "stats": {}}
        container = _make_container(raw)
        with (
            patch("app.services.container_service._get_client"),
            patch(
                "app.services.container_service._get_container",
                return_value=container,
            ),
        ):
            stats = container_service.get_stats("abc123def456")

        assert stats.memory_percent is None
        assert stats.memory_usage_bytes == 100

    def test_raises_when_docker_stats_fails(self) -> None:
        container = _make_container({})
        container.stats.side_effect = RuntimeError("boom")
        with (
            patch("app.services.container_service._get_client"),
            patch(
                "app.services.container_service._get_container",
                return_value=container,
            ),
        ):
            with pytest.raises(RuntimeError, match="Gagal mengambil statistik"):
                container_service.get_stats("abc123def456")

    def test_raises_on_invalid_stats_payload(self) -> None:
        container = _make_container(["not", "a", "dict"])
        with (
            patch("app.services.container_service._get_client"),
            patch(
                "app.services.container_service._get_container",
                return_value=container,
            ),
        ):
            with pytest.raises(RuntimeError, match="tidak valid"):
                container_service.get_stats("abc123def456")


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

def test_container_metrics_requires_auth(client: TestClient) -> None:
    response = client.get("/containers/abc123/metrics")
    assert response.status_code == 401


def test_container_metrics_returns_stats(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = _register_and_login(client, _unique_user())
    monkeypatch.setattr(container_service, "get_stats", lambda _cid: _sample_stats())

    response = client.get(
        "/containers/abc123def456/metrics", headers=_auth_header(tokens)
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["container_id"] == "abc123def456"
    assert body["cpu_percent"] == 40.0
    assert body["memory"]["usage_bytes"] == 200_000_000
    assert body["memory"]["percent"] == 20.0
    assert body["network"]["rx_bytes"] == 1500
    assert body["blkio"]["write_bytes"] == 8192
    assert body["pids_current"] == 12


def test_container_metrics_missing_container_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = _register_and_login(client, _unique_user())

    def _fail(_cid: str) -> ContainerStats:
        raise RuntimeError("Container tidak ditemukan: xyz")

    monkeypatch.setattr(container_service, "get_stats", _fail)

    response = client.get("/containers/xyz/metrics", headers=_auth_header(tokens))
    assert response.status_code == 404


def test_container_metrics_docker_down_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = _register_and_login(client, _unique_user())

    def _fail(_cid: str) -> ContainerStats:
        raise RuntimeError("Tidak dapat terhubung ke Docker daemon: refused")

    monkeypatch.setattr(container_service, "get_stats", _fail)

    response = client.get("/containers/abc123/metrics", headers=_auth_header(tokens))
    assert response.status_code == 503
