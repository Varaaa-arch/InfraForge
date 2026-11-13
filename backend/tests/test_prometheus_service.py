"""Unit test untuk prometheus_service (query, parsing, range/step)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import settings
from app.services import prometheus_service


def _response(payload: dict[str, object]) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _success(data: dict[str, object]) -> dict[str, object]:
    return {"status": "success", "data": data}


# ---------------------------------------------------------------------------
# parse_range / resolve_step
# ---------------------------------------------------------------------------

class TestParseRange:
    def test_parses_supported_units(self) -> None:
        assert prometheus_service.parse_range("30m") == 1800
        assert prometheus_service.parse_range("1h") == 3600
        assert prometheus_service.parse_range("7d") == 604800

    @pytest.mark.parametrize("value", ["", "1", "1w", "abc", "1.5h", "-5m"])
    def test_rejects_invalid_format(self, value: str) -> None:
        with pytest.raises(ValueError):
            prometheus_service.parse_range(value)

    def test_rejects_too_short_range(self) -> None:
        with pytest.raises(ValueError):
            prometheus_service.parse_range("30s")

    def test_rejects_range_beyond_limit(self) -> None:
        with pytest.raises(ValueError):
            prometheus_service.parse_range("30d")


class TestResolveStep:
    def test_default_step_targets_max_points(self) -> None:
        step = prometheus_service.resolve_step(3600)
        assert step == 15
        assert 3600 / step <= settings.METRICS_MAX_POINTS

        step_24h = prometheus_service.resolve_step(86400)
        assert 86400 / step_24h <= settings.METRICS_MAX_POINTS

    def test_step_is_snapped_to_scrape_interval(self) -> None:
        assert prometheus_service.resolve_step(3600, 61) % 15 == 0

    def test_step_below_scrape_interval_is_raised(self) -> None:
        assert prometheus_service.resolve_step(3600, 1) == 15

    def test_explicit_step_respects_max_points(self) -> None:
        step = prometheus_service.resolve_step(86400, 1)
        assert 86400 / step <= settings.METRICS_MAX_POINTS


# ---------------------------------------------------------------------------
# query_range / query_instant
# ---------------------------------------------------------------------------

class TestQueryRange:
    def test_parses_series_and_points(self) -> None:
        payload = _success(
            {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {
                            "__name__": "node_cpu_seconds_total",
                            "instance": "host.docker.internal:9100",
                        },
                        "values": [[1700000000, "12.5"], [1700000060, "13.5"]],
                    }
                ],
            }
        )
        with patch(
            "app.services.prometheus_service.httpx.get",
            return_value=_response(payload),
        ) as get:
            series = prometheus_service.query_range("up", 1, 2, 15)

        assert len(series) == 1
        assert "__name__" not in series[0].labels
        assert series[0].labels["instance"] == "host.docker.internal:9100"
        assert [point.value for point in series[0].points] == [12.5, 13.5]
        params = get.call_args.kwargs["params"]
        assert params["step"] == "15"

    def test_skips_nan_and_invalid_values(self) -> None:
        payload = _success(
            {
                "result": [
                    {
                        "metric": {},
                        "values": [
                            [1700000000, "NaN"],
                            [1700000060, "+Inf"],
                            [1700000120, "5"],
                        ],
                    }
                ]
            }
        )
        with patch(
            "app.services.prometheus_service.httpx.get",
            return_value=_response(payload),
        ):
            series = prometheus_service.query_range("up", 1, 2, 15)

        assert [point.value for point in series[0].points] == [5.0]

    def test_raises_on_prometheus_error_status(self) -> None:
        with patch(
            "app.services.prometheus_service.httpx.get",
            return_value=_response({"status": "error", "error": "parse error"}),
        ):
            with pytest.raises(RuntimeError, match="parse error"):
                prometheus_service.query_range("bad{", 1, 2, 15)

    def test_raises_on_connection_error(self) -> None:
        with patch(
            "app.services.prometheus_service.httpx.get",
            side_effect=httpx.ConnectError("refused"),
        ):
            with pytest.raises(RuntimeError, match="Gagal menghubungi Prometheus"):
                prometheus_service.query_range("up", 1, 2, 15)


class TestQueryInstant:
    def test_returns_first_value(self) -> None:
        payload = _success({"result": [{"metric": {}, "value": [1700000000, "1"]}]})
        with patch(
            "app.services.prometheus_service.httpx.get",
            return_value=_response(payload),
        ):
            assert prometheus_service.query_instant("up") == 1.0

    def test_returns_none_for_empty_result(self) -> None:
        payload = _success({"result": []})
        with patch(
            "app.services.prometheus_service.httpx.get",
            return_value=_response(payload),
        ):
            assert prometheus_service.query_instant("up") is None


class TestTargets:
    def test_filters_node_exporter_targets(self) -> None:
        payload = _success(
            {
                "activeTargets": [
                    {"labels": {"job": "node-exporter", "instance": "host:9100"}},
                    {"labels": {"job": "node-exporter", "instance": "host:9100"}},
                    {"labels": {"job": "prometheus", "instance": "localhost:9090"}},
                ]
            }
        )
        with patch(
            "app.services.prometheus_service.httpx.get",
            return_value=_response(payload),
        ):
            targets = prometheus_service.list_node_exporter_targets()

        assert targets == ["host:9100"]


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------

class TestQueryBuilders:
    instance = "host.docker.internal:9100"

    def test_instance_matcher_escapes_special_characters(self) -> None:
        matcher = prometheus_service.instance_matcher('host"x')
        assert matcher == 'instance="host\\"x"'

    def test_cpu_query_uses_idle_counter(self) -> None:
        query = prometheus_service.build_cpu_query(self.instance)
        assert "node_cpu_seconds_total" in query
        assert 'mode="idle"' in query
        assert 'instance="host.docker.internal:9100"' in query

    def test_memory_query_uses_available_and_total(self) -> None:
        query = prometheus_service.build_memory_query(self.instance)
        assert "node_memory_MemAvailable_bytes" in query
        assert "node_memory_MemTotal_bytes" in query

    def test_disk_io_query_uses_io_time_counter(self) -> None:
        query = prometheus_service.build_disk_io_query(self.instance)
        assert "node_disk_io_time_seconds_total" in query

    def test_network_queries_exclude_loopback(self) -> None:
        assert 'device!="lo"' in prometheus_service.build_network_rx_query(self.instance)
        assert 'device!="lo"' in prometheus_service.build_network_tx_query(self.instance)
