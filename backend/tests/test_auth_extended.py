from typing import Any
import uuid
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
    login_response = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    return dict(login_response.json()["data"])


def test_logout_blocklists_refresh_token(client: TestClient) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    logout_response = client.post(
        "/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert logout_response.status_code == 200
    assert logout_response.json()["success"] is True

    refresh_response = client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_response.status_code == 401


def test_logout_with_invalid_token_returns_401(client: TestClient) -> None:
    response = client.post("/auth/logout", json={"refresh_token": "token-ngasal"})
    assert response.status_code == 401


def test_logout_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    log_sink.clear()
    client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert any(f"[LOGOUT] user={payload['username']}" in msg for msg in log_sink)


def test_change_password_with_wrong_current_password_returns_400(client: TestClient) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    response = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"current_password": "salah-password", "new_password": "passwordbaru123"},
    )
    assert response.status_code == 400


def test_change_password_success_and_old_password_stops_working(client: TestClient) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    change_response = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"current_password": payload["password"], "new_password": "passwordbaru123"},
    )
    assert change_response.status_code == 200
    assert change_response.json()["success"] is True

    old_login = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": "passwordbaru123"},
    )
    assert new_login.status_code == 200


def test_change_password_without_token_returns_401(client: TestClient) -> None:
    response = client.post(
        "/auth/change-password",
        json={"current_password": "whatever", "new_password": "passwordbaru123"},
    )
    assert response.status_code == 401


def test_change_password_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    log_sink.clear()
    client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"current_password": payload["password"], "new_password": "passwordbaru123"},
    )

    assert any(f"[CHANGE_PASSWORD] user={payload['username']}" in msg for msg in log_sink)