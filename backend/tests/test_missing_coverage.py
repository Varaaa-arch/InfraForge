"""
Targeted tests to close remaining missing coverage lines:
  - app/api/auth.py:64          — refresh with invalid/non-refresh token
  - app/services/project_service.py:63  — update_project with name field
  - app/services/user_service.py:17     — update_profile with new email
  - app/utils/slugify.py:11             — slugify with empty-result string
"""

import uuid

from fastapi.testclient import TestClient


def _unique_user() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "password123",
    }


def _register_and_login(client: TestClient, payload: dict[str, str]) -> dict[str, str]:
    client.post("/auth/register", json=payload)
    resp = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    return dict(resp.json()["data"])


def _auth_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ── auth.py line 64 ──────────────────────────────────────────────────────────
def test_refresh_with_invalid_token_returns_401(client: TestClient) -> None:
    """POST /auth/refresh with a garbage token must return 401."""
    response = client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401


# ── project_service.py line 63 ───────────────────────────────────────────────
def test_update_project_name(client: TestClient) -> None:
    """PATCH /{project_id} with a new name must update project.name."""
    tokens = _register_and_login(client, _unique_user())
    create_resp = client.post(
        "/projects", headers=_auth_header(tokens), json={"name": "Old Name"}
    )
    project_id = create_resp.json()["data"]["id"]

    response = client.patch(
        f"/projects/{project_id}",
        headers=_auth_header(tokens),
        json={"name": "New Name"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "New Name"


# ── user_service.py line 17 ──────────────────────────────────────────────────
def test_update_profile_email(client: TestClient) -> None:
    """PATCH /users/me with a new unique email must update user.email."""
    payload = _unique_user()
    tokens = _register_and_login(client, payload)
    new_email = f"new_{uuid.uuid4().hex[:8]}@example.com"

    response = client.patch(
        "/users/me",
        headers=_auth_header(tokens),
        json={"email": new_email},
    )
    assert response.status_code == 200
    assert response.json()["data"]["email"] == new_email


# ── slugify.py line 11 ───────────────────────────────────────────────────────
def test_slugify_empty_result_returns_uuid_fallback() -> None:
    """A string consisting only of special chars slugifies to a uuid hex fallback."""
    from app.utils.slugify import slugify

    result = slugify("---")
    # fallback must be an 8-char hex string
    assert len(result) == 8
    assert all(c in "0123456789abcdef" for c in result)
