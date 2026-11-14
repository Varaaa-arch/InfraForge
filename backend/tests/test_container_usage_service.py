"""Unit test untuk container_usage_service (usage CPU/RAM dari Prometheus)."""

from __future__ import annotations

import pytest

from app.services import container_usage_service, prometheus_service


def _sample(labels: dict[str, str], value: float) -> prometheus_service.InstantSample:
    return prometheus_service.InstantSample(labels=labels, value=value)


def _fake_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pasang query_instant_samples palsu yang meniru tiga gauge exporter."""

    def _query(promql: str) -> list[prometheus_service.InstantSample]:
        if "cpu_percent" in promql:
            return [_sample({"name": "web"}, 12.345), _sample({"name": "db"}, 1.0)]
        if "memory_bytes" in promql and "limit" not in promql:
            return [_sample({"name": "web"}, 104857600)]
        if "limit" in promql:
            return [_sample({"name": "web"}, 1073741824)]
        return []

    monkeypatch.setattr(prometheus_service, "query_instant_samples", _query)


def test_collect_usage_maps_by_container_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_samples(monkeypatch)

    usage = container_usage_service.collect_usage()

    assert set(usage) == {"web", "db"}
    assert usage["web"].cpu_percent == 12.35
    assert usage["web"].memory_usage_bytes == 104857600
    assert usage["web"].memory_limit_bytes == 1073741824


def test_collect_usage_computes_memory_percent(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_samples(monkeypatch)

    usage = container_usage_service.collect_usage()

    assert usage["web"].memory_percent == 9.77
    assert usage["db"].memory_percent is None


def test_collect_usage_returns_empty_when_prometheus_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail(_query: str) -> list[prometheus_service.InstantSample]:
        raise RuntimeError("Gagal menghubungi Prometheus: refused")

    monkeypatch.setattr(prometheus_service, "query_instant_samples", _fail)

    assert container_usage_service.collect_usage() == {}


def test_collect_usage_skips_samples_without_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prometheus_service,
        "query_instant_samples",
        lambda _query: [_sample({"service": "web"}, 5.0)],
    )

    assert container_usage_service.collect_usage() == {}
