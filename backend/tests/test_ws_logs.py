"""
Unit test untuk WebSocket tail log Loki (/ws/logs) — Fase 3.

Stream Loki di-mock; autentikasi memakai user asli di database test.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_payload() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"wslog_{suffix}",
        "email": f"wslog_{suffix}@test.com",
        "password": "pass1234",
    }


def _register_and_login(client: TestClient) -> dict[str, str]:
    user = _user_payload()
    client.post("/auth/register", json=user)
    response = client.post(
        "/auth/login",
        data={"username": user["username"], "password": user["password"]},
    )
    return dict(response.json()["data"])


def _tail_payload() -> dict:
    return {
        "streams": [
            {
                "stream": {
                    "container": "web",
                    "level": "error",
                    "stream": "stderr",
                },
                "values": [
                    ["1700000002000000000", "ERROR second"],
                    ["1700000001000000000", "ERROR first"],
                ],
            }
        ]
    }


# ---------------------------------------------------------------------------
# _tail_url
# ---------------------------------------------------------------------------

class TestTailUrl:
    def test_http_scheme_becomes_ws(self, monkeypatch: object) -> None:
        from app.config import settings
        from app.websocket.loki_logs import _tail_url

        monkeypatch.setattr(settings, "LOKI_URL", "http://localhost:3100")  # type: ignore[attr-defined]
        url = _tail_url('{container=~".+"}')

        assert url.startswith("ws://localhost:3100/loki/api/v1/tail?")
        assert "query=%7Bcontainer%3D~%22.%2B%22%7D" in url
        assert "start=" in url

    def test_https_scheme_becomes_wss(self, monkeypatch: object) -> None:
        from app.config import settings
        from app.websocket.loki_logs import _tail_url

        monkeypatch.setattr(settings, "LOKI_URL", "https://loki.example.com")  # type: ignore[attr-defined]
        url = _tail_url("{container=\"web\"}")

        assert url.startswith("wss://loki.example.com/loki/api/v1/tail?")


# ---------------------------------------------------------------------------
# parse_tail_payload
# ---------------------------------------------------------------------------

class TestParseTailPayload:
    def test_parses_and_sorts_entries(self) -> None:
        from app.websocket.loki_logs import parse_tail_payload

        entries = parse_tail_payload(_tail_payload())

        assert [entry["line"] for entry in entries] == [
            "ERROR first",
            "ERROR second",
        ]
        assert entries[0]["timestamp"] == "2023-11-14T22:13:21+00:00"
        assert entries[0]["timestamp_ns"] == "1700000001000000000"
        assert entries[0]["level"] == "error"
        assert entries[0]["container"] == "web"
        assert entries[0]["stream"] == "stderr"

    def test_falls_back_to_detected_level(self) -> None:
        from app.websocket.loki_logs import parse_tail_payload

        payload = {
            "streams": [
                {
                    "stream": {"container": "web", "detected_level": "warn"},
                    "values": [["1700000001000000000", "careful"]],
                }
            ]
        }
        entries = parse_tail_payload(payload)

        assert entries[0]["level"] == "warn"

    def test_skips_incomplete_values(self) -> None:
        from app.websocket.loki_logs import parse_tail_payload

        payload = {
            "streams": [
                {"stream": {}, "values": [["1700000001000000000"], []]}
            ]
        }
        assert parse_tail_payload(payload) == []

    def test_empty_payload_returns_empty_list(self) -> None:
        from app.websocket.loki_logs import parse_tail_payload

        assert parse_tail_payload({}) == []


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

class TestWebSocketLogs:
    def test_invalid_token_sends_error(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/logs?token=invalid_token") as ws:
            message = ws.receive_json()
        assert "Token tidak valid" in message["error"]

    def test_missing_token_rejected(self, client: TestClient) -> None:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/logs"):
                pass

    def test_refresh_token_rejected(self, client: TestClient) -> None:
        tokens = _register_and_login(client)
        with client.websocket_connect(
            f"/ws/logs?token={tokens['refresh_token']}"
        ) as ws:
            message = ws.receive_json()
        assert "Token tidak valid" in message["error"]

    def test_invalid_level_sends_error(
        self, client: TestClient, db_session: object
    ) -> None:
        tokens = _register_and_login(client)
        with patch(
            "app.websocket.loki_logs._get_db_session", return_value=db_session
        ):
            with client.websocket_connect(
                f"/ws/logs?token={tokens['access_token']}&level=critical"
            ) as ws:
                message = ws.receive_json()
        assert "Level tidak valid" in message["error"]

    def test_invalid_container_sends_error(
        self, client: TestClient, db_session: object
    ) -> None:
        tokens = _register_and_login(client)
        with patch(
            "app.websocket.loki_logs._get_db_session", return_value=db_session
        ):
            with client.websocket_connect(
                f"/ws/logs?token={tokens['access_token']}&container=bad!name"
            ) as ws:
                message = ws.receive_json()
        assert "Nama container tidak valid" in message["error"]

    def test_stream_forwards_entries_with_expected_query(
        self, client: TestClient, db_session: object
    ) -> None:
        tokens = _register_and_login(client)
        captured: dict[str, str] = {}

        async def fake_stream(websocket: object, query: str) -> None:
            captured["query"] = query
            await websocket.send_json(  # type: ignore[attr-defined]
                {
                    "timestamp": "2023-11-14T22:13:21+00:00",
                    "timestamp_ns": "1700000001000000000",
                    "line": "ERROR boom",
                    "level": "error",
                    "container": "web",
                    "stream": "stderr",
                }
            )

        with (
            patch(
                "app.websocket.loki_logs._get_db_session", return_value=db_session
            ),
            patch("app.websocket.loki_logs._stream_loki", new=fake_stream),
        ):
            with client.websocket_connect(
                f"/ws/logs?token={tokens['access_token']}"
                "&container=web&level=error&q=boom"
            ) as ws:
                message = ws.receive_json()

        assert message["line"] == "ERROR boom"
        assert message["level"] == "error"
        assert captured["query"] == (
            '{container="web", level=~"error|err|critical|fatal"} |= "boom"'
        )

    def test_stream_without_filters_uses_global_query(
        self, client: TestClient, db_session: object
    ) -> None:
        tokens = _register_and_login(client)
        captured: dict[str, str] = {}

        async def fake_stream(websocket: object, query: str) -> None:
            captured["query"] = query

        with (
            patch(
                "app.websocket.loki_logs._get_db_session", return_value=db_session
            ),
            patch("app.websocket.loki_logs._stream_loki", new=fake_stream),
        ):
            with client.websocket_connect(
                f"/ws/logs?token={tokens['access_token']}"
            ):
                pass

        assert captured["query"] == '{container=~".+"}'

    def test_loki_failure_sends_error(
        self, client: TestClient, db_session: object
    ) -> None:
        tokens = _register_and_login(client)

        async def failing_stream(websocket: object, query: str) -> None:
            raise RuntimeError("Loki mati")

        with (
            patch(
                "app.websocket.loki_logs._get_db_session", return_value=db_session
            ),
            patch("app.websocket.loki_logs._stream_loki", new=failing_stream),
        ):
            with client.websocket_connect(
                f"/ws/logs?token={tokens['access_token']}"
            ) as ws:
                message = ws.receive_json()

        assert "Gagal streaming log" in message["error"]
