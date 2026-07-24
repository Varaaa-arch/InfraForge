"""
Test untuk menutup missing coverage di:
  - app/core/exception_handler.py line 33-34 : unhandled Exception → 500
  - app/database/redis_client.py  line 18-20 : check_redis_connection() failure
  - app/database/session.py       line 18-22 : check_database_connection() success
                                  line 31-33 : check_database_connection() failure
"""

from unittest.mock import MagicMock, patch

import redis
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database.redis_client import check_redis_connection
from app.database.session import check_database_connection


# ── exception_handler.py line 33-34 ─────────────────────────────────────────
def test_unhandled_exception_returns_500() -> None:
    """Route yang raise Exception biasa harus ditangkap → 500 Internal Server Error."""
    from app.main import app as fastapi_app

    @fastapi_app.get("/test-500-exception")
    def _raise_unhandled() -> None:
        raise RuntimeError("something totally unexpected")

    # raise_server_exceptions=False supaya exception diteruskan ke handler,
    # bukan di-raise langsung ke test
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        response = c.get("/test-500-exception")

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["code"] == 500
    assert body["message"] == "Internal Server Error"

    # Cleanup — hapus route test supaya tidak bocor ke test lain
    fastapi_app.routes[:] = [r for r in fastapi_app.routes if getattr(r, "path", "") != "/test-500-exception"]


# ── redis_client.py line 18-20 ───────────────────────────────────────────────
def test_check_redis_connection_returns_true_when_ok() -> None:
    """ping() berhasil → return True."""
    with patch("app.database.redis_client.redis_client") as mock_redis:
        mock_redis.ping.return_value = True
        result = check_redis_connection()

    assert result is True


def test_check_redis_connection_returns_false_when_down() -> None:
    """ping() raise ConnectionError → return False, tidak crash."""
    with patch("app.database.redis_client.redis_client") as mock_redis:
        mock_redis.ping.side_effect = redis.ConnectionError("Redis down")
        result = check_redis_connection()

    assert result is False


def test_check_redis_connection_logs_warning_when_down() -> None:
    """Pastikan warning di-log saat Redis tidak bisa dijangkau."""
    with patch("app.database.redis_client.redis_client") as mock_redis:
        mock_redis.ping.side_effect = redis.ConnectionError("refused")

        with patch("app.database.redis_client.logger") as mock_logger:
            result = check_redis_connection()

        assert result is False
        mock_logger.warning.assert_called_once()


# ── session.py line 18-22 (success) & 31-33 (failure) ───────────────────────
def test_check_database_connection_returns_true_when_ok() -> None:
    """SELECT 1 berhasil → return True."""
    mock_conn = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.database.session.engine") as mock_engine:
        mock_engine.connect.return_value = mock_ctx
        result = check_database_connection()

    assert result is True


def test_check_database_connection_returns_false_when_down() -> None:
    """engine.connect() raise Exception → return False, tidak crash."""
    with patch("app.database.session.engine") as mock_engine:
        mock_engine.connect.side_effect = OperationalError("conn", {}, Exception("down"))
        result = check_database_connection()

    assert result is False


def test_check_database_connection_logs_warning_when_down() -> None:
    """Pastikan warning di-log saat DB tidak bisa dijangkau."""
    with patch("app.database.session.engine") as mock_engine:
        mock_engine.connect.side_effect = Exception("db unreachable")

        with patch("app.database.session.logger") as mock_logger:
            result = check_database_connection()

        assert result is False
        mock_logger.warning.assert_called_once()


# ── health endpoint — ready with DB/Redis down ───────────────────────────────
def test_ready_endpoint_returns_503_when_db_down(client: TestClient) -> None:
    """/ready harus return 503 dan status 'down' kalau DB tidak bisa dijangkau."""
    with patch("app.api.health.check_database_connection", return_value=False):
        with patch("app.api.health.check_redis_connection", return_value=True):
            response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["data"]["database"] == "down"
    assert body["data"]["redis"] == "up"


def test_ready_endpoint_returns_503_when_redis_down(client: TestClient) -> None:
    """/ready harus return 503 dan status 'down' kalau Redis tidak bisa dijangkau."""
    with patch("app.api.health.check_database_connection", return_value=True):
        with patch("app.api.health.check_redis_connection", return_value=False):
            response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["data"]["redis"] == "down"
    assert body["data"]["database"] == "up"
