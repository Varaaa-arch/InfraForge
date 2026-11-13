"""Test untuk GET /servers/{id}/metrics dan server_metrics_service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
import pytest
from fastapi.testclient import TestClient

from app.models.server import Server
from app.services import prometheus_service, server_metrics_service


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


def _server_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "prod-server",
        "host": "192.0.2.10",
        "username": "deploy",
        "auth_type": "password",
        "password": "secret123",
        "exporter_instance": "host.docker.internal:9100",
    }
    payload.update(overrides)
    return payload


def _create_server(client: TestClient, tokens: dict[str, str], **overrides: object) -> int:
    response = client.post(
        "/servers", headers=_auth_header(tokens), json=_server_payload(**overrides)
    )
    return int(response.json()["data"]["id"])


def _sample_series(value: float = 42.0) -> list[prometheus_service.PrometheusSeries]:
    return [
        prometheus_service.PrometheusSeries(
            labels={"instance": "host.docker.internal:9100"},
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

def test_collect_without_exporter_instance_returns_unavailable() -> None:
    server = Server(id=1, name="Demo", exporter_instance=None)

    result = server_metrics_service.collect(server, "1h")

    assert result.available is False
    assert result.exporter_instance is None
    assert result.series == {}
    assert "belum dikonfigurasi" in (result.message or "")


def test_collect_unregistered_target_returns_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server(id=1, name="Demo", exporter_instance="10.0.0.1:9100")
    monkeypatch.setattr(prometheus_service, "query_instant", lambda _query: None)

    result = server_metrics_service.collect(server, "1h")

    assert result.available is False
    assert "belum terdaftar" in (result.message or "")


def test_collect_down_target_returns_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server(id=1, name="Demo", exporter_instance="10.0.0.1:9100")
    monkeypatch.setattr(prometheus_service, "query_instant", lambda _query: 0.0)

    result = server_metrics_service.collect(server, "1h")

    assert result.available is False
    assert "down" in (result.message or "")


def test_collect_returns_series_with_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server(
        id=1, name="Demo", exporter_instance="host.docker.internal:9100"
    )
    monkeypatch.setattr(prometheus_service, "query_instant", lambda _query: 1.0)
    monkeypatch.setattr(
        prometheus_service, "query_range", lambda *_args, **_kwargs: _sample_series(42.0)
    )

    result = server_metrics_service.collect(server, "1h")

    assert result.available is True
    assert result.message is None
    assert set(result.series) == {
        "cpu_percent",
        "memory_percent",
        "disk_usage_percent",
        "disk_io_percent",
        "network_rx_bytes",
        "network_tx_bytes",
    }
    assert result.series["cpu_percent"].summary is not None
    assert result.series["cpu_percent"].summary.current == 42.0
    assert result.step_seconds % 15 == 0
    assert result.generated_at


def test_collect_propagates_prometheus_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server(
        id=1, name="Demo", exporter_instance="host.docker.internal:9100"
    )

    def _fail(_query: str) -> float:
        raise RuntimeError("Gagal menghubungi Prometheus: refused")

    monkeypatch.setattr(prometheus_service, "query_instant", _fail)

    with pytest.raises(RuntimeError, match="Gagal menghubungi Prometheus"):
        server_metrics_service.collect(server, "1h")


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

def test_server_metrics_requires_auth(client: TestClient) -> None:
    response = client.get("/servers/1/metrics")
    assert response.status_code == 401


def test_server_metrics_other_owner_returns_404(client: TestClient) -> None:
    tokens_a = _register_and_login(client, _unique_user())
    tokens_b = _register_and_login(client, _unique_user())
    server_id = _create_server(client, tokens_a)

    response = client.get(
        f"/servers/{server_id}/metrics", headers=_auth_header(tokens_b)
    )
    assert response.status_code == 404


def test_server_metrics_invalid_range_returns_400(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    server_id = _create_server(client, tokens)

    response = client.get(
        f"/servers/{server_id}/metrics?range=abc", headers=_auth_header(tokens)
    )
    assert response.status_code == 400
    assert "range" in response.json()["message"]


def test_server_metrics_without_exporter_returns_available_false(
    client: TestClient,
) -> None:
    tokens = _register_and_login(client, _unique_user())
    server_id = _create_server(client, tokens, exporter_instance=None)

    response = client.get(
        f"/servers/{server_id}/metrics", headers=_auth_header(tokens)
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["available"] is False
    assert body["series"] == {}
    assert body["step_seconds"] == 15


def test_server_metrics_returns_503_when_prometheus_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = _register_and_login(client, _unique_user())
    server_id = _create_server(client, tokens)

    def _fail(_query: str) -> float:
        raise RuntimeError("Gagal menghubungi Prometheus: refused")

    monkeypatch.setattr(server_metrics_service.prometheus_service, "query_instant", _fail)

    response = client.get(
        f"/servers/{server_id}/metrics", headers=_auth_header(tokens)
    )

    assert response.status_code == 503
    assert "Prometheus" in response.json()["message"]


def test_server_metrics_returns_series(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = _register_and_login(client, _unique_user())
    server_id = _create_server(client, tokens)
    monkeypatch.setattr(
        server_metrics_service.prometheus_service, "query_instant", lambda _query: 1.0
    )
    monkeypatch.setattr(
        server_metrics_service.prometheus_service,
        "query_range",
        lambda *_args, **_kwargs: _sample_series(12.5),
    )

    response = client.get(
        f"/servers/{server_id}/metrics?range=6h&step=60",
        headers=_auth_header(tokens),
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["available"] is True
    assert body["range"] == "6h"
    assert body["step_seconds"] == 90
    assert body["series"]["cpu_percent"]["unit"] == "%"
    assert body["series"]["cpu_percent"]["summary"]["current"] == 12.5
    assert len(body["series"]["cpu_percent"]["points"]) == 1
    assert body["exporter_instance"] == "host.docker.internal:9100"
