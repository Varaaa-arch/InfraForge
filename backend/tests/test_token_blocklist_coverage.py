"""
Test untuk menutup missing coverage di app/services/token_blocklist.py:
  - line 20     : blocklist_token() dengan expires_in_seconds <= 0 (early return)
  - line 23-24  : blocklist_token() — Redis raise Exception → log warning
  - line 35-37  : is_blocklisted()  — Redis raise Exception → log warning, return False
"""

from unittest.mock import MagicMock, patch

import pytest
import redis

from app.services.token_blocklist import blocklist_token, is_blocklisted


# ── token_blocklist.py line 20 ───────────────────────────────────────────────
def test_blocklist_token_skips_when_expires_nonpositive() -> None:
    """TTL <= 0 harus langsung return tanpa menyentuh Redis sama sekali."""
    with patch("app.services.token_blocklist.redis_client") as mock_redis:
        blocklist_token("some-jti", 0)
        blocklist_token("some-jti", -5)

    mock_redis.set.assert_not_called()


# ── token_blocklist.py line 23-24 ────────────────────────────────────────────
def test_blocklist_token_logs_warning_when_redis_down() -> None:
    """Redis raise exception → fungsi log warning dan tidak crash."""
    with patch("app.services.token_blocklist.redis_client") as mock_redis:
        mock_redis.set.side_effect = redis.ConnectionError("Redis down")

        # Tidak boleh raise exception ke caller
        blocklist_token("jti-abc", 300)


def test_blocklist_token_warning_message_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Pastikan warning benar-benar di-log saat Redis down."""
    import logging

    with patch("app.services.token_blocklist.redis_client") as mock_redis:
        mock_redis.set.side_effect = Exception("koneksi gagal")

        with patch("app.services.token_blocklist.logger") as mock_logger:
            blocklist_token("jti-xyz", 100)
            mock_logger.warning.assert_called_once()
            msg = mock_logger.warning.call_args[0][0]
            assert "redis" in msg.lower() or "blocklist" in msg.lower()


# ── token_blocklist.py line 35-37 ────────────────────────────────────────────
def test_is_blocklisted_returns_false_when_redis_down() -> None:
    """Redis raise exception → fail open, return False, tidak crash."""
    with patch("app.services.token_blocklist.redis_client") as mock_redis:
        mock_redis.exists.side_effect = redis.ConnectionError("Redis down")

        result = is_blocklisted("jti-abc")

    assert result is False


def test_is_blocklisted_warning_message_logged() -> None:
    """Pastikan warning di-log saat Redis down pada is_blocklisted."""
    with patch("app.services.token_blocklist.redis_client") as mock_redis:
        mock_redis.exists.side_effect = Exception("timeout")

        with patch("app.services.token_blocklist.logger") as mock_logger:
            result = is_blocklisted("jti-xyz")

            assert result is False
            mock_logger.warning.assert_called_once()
            msg = mock_logger.warning.call_args[0][0]
            assert "redis" in msg.lower() or "blocklist" in msg.lower()


def test_is_blocklisted_returns_true_when_key_exists() -> None:
    """Pastikan return True saat key ada di Redis."""
    with patch("app.services.token_blocklist.redis_client") as mock_redis:
        mock_redis.exists.return_value = 1

        result = is_blocklisted("jti-exists")

    assert result is True


def test_is_blocklisted_returns_false_when_key_absent() -> None:
    """Pastikan return False saat key tidak ada di Redis."""
    with patch("app.services.token_blocklist.redis_client") as mock_redis:
        mock_redis.exists.return_value = 0

        result = is_blocklisted("jti-missing")

    assert result is False
