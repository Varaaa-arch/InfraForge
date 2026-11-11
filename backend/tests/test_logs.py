"""
Unit test untuk Centralized Logging (Loki) — Fase 2.

Semua request HTTP ke Loki di-mock; tidak butuh Loki berjalan.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _loki_response(result: list[dict] | None = None) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "status": "success",
        "data": {"resultType": "streams", "result": result or []},
    }
    return response


def _stream(
    values: list[list[str]],
    container: str = "web",
    level: str | None = "info",
    stream: str = "stdout",
) -> dict:
    labels = {"container": container, "stream": stream}
    if level is not None:
        labels["level"] = level
    return {"stream": labels, "values": values}


# ---------------------------------------------------------------------------
# build_query
# ---------------------------------------------------------------------------

class TestBuildQuery:
    def test_default_matches_all_containers(self) -> None:
        from app.services.loki_service import build_query

        assert build_query() == '{container=~".+"}'

    def test_container_level_and_keyword(self) -> None:
        from app.services.loki_service import build_query

        query = build_query(
            container="infraforge-backend", level="error", keyword="boom"
        )
        assert query == (
            '{container="infraforge-backend", level=~"error|err|critical|fatal"}'
            ' |= "boom"'
        )

    def test_warning_uses_regex_variants(self) -> None:
        from app.services.loki_service import build_query

        query = build_query(level="warning")
        assert 'level=~"warn|warning"' in query

    def test_level_all_is_ignored(self) -> None:
        from app.services.loki_service import build_query

        assert "level" not in build_query(level="all")

    def test_keyword_quotes_are_escaped(self) -> None:
        from app.services.loki_service import build_query

        query = build_query(keyword='say "hi"')
        assert '|= "say \\"hi\\""' in query

    def test_invalid_container_raises(self) -> None:
        from app.services.loki_service import build_query

        with pytest.raises(ValueError, match="Nama container tidak valid"):
            build_query(container="bad name!")

    def test_invalid_level_raises(self) -> None:
        from app.services.loki_service import build_query

        with pytest.raises(ValueError, match="Level tidak valid"):
            build_query(level="critical")

    def test_invalid_last_raises(self) -> None:
        from app.services.loki_service import _parse_last

        with pytest.raises(ValueError, match="Format `last` tidak valid"):
            _parse_last("1hour")

    def test_last_beyond_retention_raises(self) -> None:
        from app.services.loki_service import _parse_last

        with pytest.raises(ValueError, match="7 hari"):
            _parse_last("8d")


# ---------------------------------------------------------------------------
# query_logs
# ---------------------------------------------------------------------------

class TestQueryLogs:
    def test_parses_entries_and_sorts_ascending(self) -> None:
        from app.services.loki_service import query_logs

        response = _loki_response(
            [
                _stream(
                    [
                        ["1700000002000000000", "second"],
                        ["1700000001000000000", "first"],
                    ],
                    level="error",
                    stream="stderr",
                )
            ]
        )
        with patch("app.services.loki_service.httpx.get", return_value=response):
            result = query_logs(container="web")

        assert [entry.line for entry in result.entries] == ["first", "second"]
        assert result.entries[0].timestamp == "2023-11-14T22:13:21+00:00"
        assert result.entries[0].timestamp_ns == "1700000001000000000"
        assert result.entries[0].level == "error"
        assert result.entries[0].container == "web"
        assert result.entries[0].stream == "stderr"
        assert result.query == '{container="web"}'

    def test_falls_back_to_detected_level(self) -> None:
        from app.services.loki_service import query_logs

        response = _loki_response(
            [_stream([["1700000001000000000", "line"]], level=None)]
        )
        response.json.return_value["data"]["result"][0]["stream"][
            "detected_level"
        ] = "warn"

        with patch("app.services.loki_service.httpx.get", return_value=response):
            result = query_logs()

        assert result.entries[0].level == "warn"

    def test_sends_expected_params(self) -> None:
        from app.services.loki_service import query_logs

        response = _loki_response([])
        with patch(
            "app.services.loki_service.httpx.get", return_value=response
        ) as mock_get:
            query_logs(level="info", keyword="GET", last="30m", limit=50)

        args, kwargs = mock_get.call_args
        assert args[0] == "http://localhost:3100/loki/api/v1/query_range"
        params = kwargs["params"]
        assert params["query"] == '{container=~".+", level="info"} |= "GET"'
        assert params["limit"] == "50"
        assert params["direction"] == "backward"
        assert int(params["end"]) > int(params["start"])

    def test_empty_result_returns_no_entries(self) -> None:
        from app.services.loki_service import query_logs

        with patch(
            "app.services.loki_service.httpx.get", return_value=_loki_response([])
        ):
            result = query_logs()

        assert result.entries == []

    def test_http_error_raises_runtime_error(self) -> None:
        from app.services.loki_service import query_logs

        with patch(
            "app.services.loki_service.httpx.get",
            side_effect=httpx.ConnectError("refused"),
        ):
            with pytest.raises(RuntimeError, match="Gagal menghubungi Loki"):
                query_logs()


# ---------------------------------------------------------------------------
# list_containers
# ---------------------------------------------------------------------------

class TestListContainers:
    def test_returns_sorted_names(self) -> None:
        from app.services.loki_service import list_containers

        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "success", "data": ["web", "api"]}

        with patch("app.services.loki_service.httpx.get", return_value=response):
            containers = list_containers()

        assert containers == ["api", "web"]

    def test_http_error_raises_runtime_error(self) -> None:
        from app.services.loki_service import list_containers

        with patch(
            "app.services.loki_service.httpx.get",
            side_effect=httpx.ConnectTimeout("timeout"),
        ):
            with pytest.raises(RuntimeError, match="Gagal menghubungi Loki"):
                list_containers()


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class TestLogEndpoints:
    def _login(self, client: object) -> dict[str, str]:
        import uuid

        from fastapi.testclient import TestClient

        c: TestClient = client  # type: ignore[assignment]
        suffix = uuid.uuid4().hex[:8]
        user = {
            "username": f"u_{suffix}",
            "email": f"u_{suffix}@x.com",
            "password": "pass1234",
        }
        c.post("/auth/register", json=user)
        r = c.post(
            "/auth/login",
            data={"username": user["username"], "password": user["password"]},
        )
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    def test_search_logs_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient

        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        response = _loki_response(
            [_stream([["1700000001000000000", "hello"], ["1700000002000000000", "world"]])]
        )

        with patch("app.services.loki_service.httpx.get", return_value=response):
            r = c.get("/logs?container=web&last=1h", headers=headers)

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["count"] == 2
        assert data["query"] == '{container="web"}'
        assert data["logs"][0]["line"] == "hello"
        assert data["logs"][1]["line"] == "world"

    def test_search_logs_requires_auth(self, client: object) -> None:
        from fastapi.testclient import TestClient

        c: TestClient = client  # type: ignore[assignment]
        assert c.get("/logs").status_code == 401

    def test_invalid_level_returns_422(self, client: object) -> None:
        from fastapi.testclient import TestClient

        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        r = c.get("/logs?level=critical", headers=headers)
        assert r.status_code == 422

    def test_invalid_container_returns_400(self, client: object) -> None:
        from fastapi.testclient import TestClient

        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        r = c.get("/logs?container=bad!name", headers=headers)
        assert r.status_code == 400

    def test_loki_unavailable_returns_503(self, client: object) -> None:
        from fastapi.testclient import TestClient

        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)

        with patch(
            "app.services.loki_service.httpx.get",
            side_effect=httpx.ConnectError("refused"),
        ):
            r = c.get("/logs", headers=headers)

        assert r.status_code == 503

    def test_list_containers_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient

        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "success",
            "data": ["infraforge-backend", "web"],
        }

        with patch("app.services.loki_service.httpx.get", return_value=response):
            r = c.get("/logs/containers", headers=headers)

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["count"] == 2
        assert data["containers"] == ["infraforge-backend", "web"]

    def test_list_containers_requires_auth(self, client: object) -> None:
        from fastapi.testclient import TestClient

        c: TestClient = client  # type: ignore[assignment]
        assert c.get("/logs/containers").status_code == 401

    def test_cors_preflight_allows_frontend_origin(self, client: object) -> None:
        from fastapi.testclient import TestClient

        c: TestClient = client  # type: ignore[assignment]
        r = c.options(
            "/logs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == "http://localhost:5173"

        r2 = c.options(
            "/logs",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r2.status_code == 200
        assert r2.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
