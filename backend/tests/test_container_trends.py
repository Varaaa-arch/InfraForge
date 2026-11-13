"""Test untuk GET /containers/usage/top dan container_trends_service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.services import container_trends_service, prometheus_service


def _unique_user() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "password123",
    }


def _register_and_login(client: TestClient, payload: dict[str, str]) -> dict[str, str]:
    client.post("/auth/register", json=payload)
    response = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    return dict(response.json()["data"])


def _auth_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _sample(labels: dict[str, str], value: float) -> prometheus_service.InstantSample:
    return prometheus_service.InstantSample(labels=labels, value=value)


def _range_series(
    value: float = 11.0,
) -> list[prometheus_service.PrometheusSeries]:
    return [
        prometheus_service.PrometheusSeries(
            labels={"name": "web"},
            points=[
                prometheus_service.MetricPoint(
                    timestamp=datetime.now(tz=UTC), value=value
                )
            ],
        )
    ]


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------

def test_collect_maps_top_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    def _instant(query: str) -> list[prometheus_service.InstantSample]:
        if "infraforge_container_memory_bytes" in query:
            return [_sample({"name": "web"}, 104857600)]
        return [
            _sample(
                {
                    "name": "web",
                    "service": "web",
                    "compose_project": "infraforge",
                    "image": "nginx:latest",
                },
                12.5,
            )
        ]

    monkeypatch.setattr(prometheus_service, "query_instant_samples", _instant)
    monkeypatch.setattr(
        prometheus_service, "query_range", lambda *_args, **_kwargs: _range_series(11.0)
    )

    result = container_trends_service.collect("1h", 5)

    assert result.available is True
    assert result.range == "1h"
    assert result.step_seconds % 15 == 0
    assert len(result.containers) == 1

    container = result.containers[0]
    assert container.name == "web"
    assert container.service == "web"
    assert container.compose_project == "infraforge"
    assert container.image == "nginx:latest"
    assert container.cpu_percent == 12.5
    assert container.memory_bytes == 104857600
    assert container.cpu_points[0].value == 11.0


def test_collect_returns_empty_when_no_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        prometheus_service, "query_instant_samples", lambda _query: []
    )

    result = container_trends_service.collect("1h")

    assert result.available is True
    assert result.containers == []
    assert "Belum ada data" in (result.message or "")


def test_collect_skips_container_with_failing_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prometheus_service,
        "query_instant_samples",
        lambda _query: [_sample({"name": "web"}, 5.0)],
    )

    def _fail(*_args: object, **_kwargs: object) -> list[prometheus_service.PrometheusSeries]:
        raise RuntimeError("Prometheus menolak query")

    monkeypatch.setattr(prometheus_service, "query_range", _fail)

    result = container_trends_service.collect("1h")

    assert result.available is True
    assert result.containers == []


def test_collect_propagates_prometheus_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail(_query: str) -> list[prometheus_service.InstantSample]:
        raise RuntimeError("Gagal menghubungi Prometheus: refused")

    monkeypatch.setattr(prometheus_service, "query_instant_samples", _fail)

    with pytest.raises(RuntimeError, match="Gagal menghubungi Prometheus"):
        container_trends_service.collect("1h")


def test_collect_rejects_invalid_range() -> None:
    with pytest.raises(ValueError):
        container_trends_service.collect("abc")


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

def test_top_usage_requires_auth(client: TestClient) -> None:
    response = client.get("/containers/usage/top")
    assert response.status_code == 401


def test_top_usage_invalid_range_returns_400(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())

    response = client.get(
        "/containers/usage/top?range=abc", headers=_auth_header(tokens)
    )

    assert response.status_code == 400
    assert "range" in response.json()["message"]


def test_top_usage_returns_containers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = _register_and_login(client, _unique_user())

    def _instant(query: str) -> list[prometheus_service.InstantSample]:
        if "infraforge_container_memory_bytes" in query:
            return [_sample({"name": "web"}, 2048)]
        return [_sample({"name": "web", "service": "web"}, 7.5)]

    monkeypatch.setattr(prometheus_service, "query_instant_samples", _instant)
    monkeypatch.setattr(
        prometheus_service, "query_range", lambda *_args, **_kwargs: _range_series(7.0)
    )

    response = client.get(
        "/containers/usage/top?range=15m&limit=3", headers=_auth_header(tokens)
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["available"] is True
    assert body["range"] == "15m"
    assert body["containers"][0]["name"] == "web"
    assert body["containers"][0]["cpu_percent"] == 7.5
    assert body["containers"][0]["memory_bytes"] == 2048


def test_top_usage_prometheus_down_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = _register_and_login(client, _unique_user())

    def _fail(_query: str) -> list[prometheus_service.InstantSample]:
        raise RuntimeError("Gagal menghubungi Prometheus: refused")

    monkeypatch.setattr(
        container_trends_service.prometheus_service, "query_instant_samples", _fail
    )

    response = client.get(
        "/containers/usage/top", headers=_auth_header(tokens)
    )

    assert response.status_code == 503
    assert "Prometheus" in response.json()["message"]
