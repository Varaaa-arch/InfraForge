"""
Test untuk menutup missing coverage di app/api/deps.py:
  - line 16     : decode_token() return None  → 401
  - line 30     : token type bukan "access"   → 401
  - line 37-38  : sub (user_id) tidak ada di payload → 401
  - line 45-46  : sub ada tapi bukan integer (ValueError) → 401
  - line 54     : user tidak ditemukan di DB  → 401
"""

import uuid
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient


def _unique_user() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "password123",
    }


def _register_and_login(client: TestClient, payload: dict[str, str]) -> dict[str, Any]:
    client.post("/auth/register", json=payload)
    resp = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    return dict(resp.json()["data"])


# ── deps.py line 16 ──────────────────────────────────────────────────────────
def test_get_current_user_invalid_token_decode_returns_401(client: TestClient) -> None:
    """decode_token() return None → HTTPException 401."""
    with patch("app.api.deps.decode_token", return_value=None):
        response = client.get("/auth/me", headers={"Authorization": "Bearer sometoken"})

    assert response.status_code == 401


# ── deps.py line 30 ──────────────────────────────────────────────────────────
def test_get_current_user_with_refresh_token_returns_401(client: TestClient) -> None:
    """Token bertipe 'refresh' tidak boleh dipakai sebagai access token."""
    payload = _unique_user()
    tokens = _register_and_login(client, payload)
    refresh_token = tokens["refresh_token"]

    response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert response.status_code == 401


# ── deps.py line 37-38 ───────────────────────────────────────────────────────
def test_get_current_user_missing_sub_returns_401(client: TestClient) -> None:
    """Payload valid tapi tidak ada field 'sub' → 401."""
    with patch(
        "app.api.deps.decode_token",
        return_value={"type": "access"},  # tidak ada "sub"
    ):
        response = client.get("/auth/me", headers={"Authorization": "Bearer sometoken"})

    assert response.status_code == 401


# ── deps.py line 45-46 ───────────────────────────────────────────────────────
def test_get_current_user_non_integer_sub_returns_401(client: TestClient) -> None:
    """sub ada tapi bukan angka → ValueError → 401."""
    with patch(
        "app.api.deps.decode_token",
        return_value={"type": "access", "sub": "bukan-angka"},
    ):
        response = client.get("/auth/me", headers={"Authorization": "Bearer sometoken"})

    assert response.status_code == 401


# ── deps.py line 54 ──────────────────────────────────────────────────────────
def test_get_current_user_user_not_in_db_returns_401(client: TestClient) -> None:
    """Token valid, user_id valid, tapi user sudah tidak ada di DB → 401."""
    with patch(
        "app.api.deps.decode_token",
        return_value={"type": "access", "sub": "99999999"},
    ):
        with patch("app.api.deps.auth_service.get_user_by_id", return_value=None):
            response = client.get(
                "/auth/me", headers={"Authorization": "Bearer sometoken"}
            )

    assert response.status_code == 401
    assert response.json()["success"] is False
