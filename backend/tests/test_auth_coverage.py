"""
Test untuk menutup missing coverage di app/api/auth.py:
  - line 36 : register dengan email duplikat
  - line 64 : refresh token dengan user tidak ditemukan di DB
  - line 73 : refresh token yang sudah di-blocklist
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


# ── auth.py line 36 ──────────────────────────────────────────────────────────
def test_register_duplicate_email_returns_400(client: TestClient) -> None:
    """Email yang sama tapi username berbeda harus ditolak 400."""
    first = _unique_user()
    client.post("/auth/register", json=first)

    second = _unique_user()
    second["email"] = first["email"]  # sama emailnya, username beda

    response = client.post("/auth/register", json=second)
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert "email" in body["message"].lower()


# ── auth.py line 64 ──────────────────────────────────────────────────────────
def test_refresh_returns_401_when_user_not_found(client: TestClient) -> None:
    """Refresh token valid secara kriptografi tapi user-nya sudah hilang dari DB."""
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    # Mock get_user_by_id supaya seolah user sudah tidak ada
    with patch("app.api.auth.auth_service.get_user_by_id", return_value=None):
        response = client.post(
            "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert "ditemukan" in body["message"].lower()


# ── auth.py line 73 ──────────────────────────────────────────────────────────
def test_refresh_returns_401_when_token_is_blocklisted(client: TestClient) -> None:
    """Refresh token yang JTI-nya sudah masuk blocklist harus ditolak."""
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    # Simulasi JTI sudah ada di blocklist
    with patch("app.api.auth.token_blocklist.is_blocklisted", return_value=True):
        response = client.post(
            "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert "berlaku" in body["message"].lower()
