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
    login_response = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    return login_response.json()["data"]  # type: ignore[no-any-return]


def test_get_profile(client: TestClient) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    response = client.get(
        "/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["username"] == payload["username"]
    assert body["full_name"] is None
    assert body["is_active"] is True


def test_get_profile_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/users/me")
    assert response.status_code == 401


def test_update_full_name(client: TestClient) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    response = client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"full_name": "John Smith"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["full_name"] == "John Smith"


def test_update_username_then_login_with_new_username(client: TestClient) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)
    new_username = f"renamed_{uuid.uuid4().hex[:8]}"

    response = client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"username": new_username},
    )
    assert response.status_code == 200
    assert response.json()["data"]["username"] == new_username

    login_response = client.post(
        "/auth/login", data={"username": new_username, "password": payload["password"]}
    )
    assert login_response.status_code == 200


def test_update_username_rejects_duplicate(client: TestClient) -> None:
    first = _unique_user()
    second = _unique_user()
    client.post("/auth/register", json=first)
    tokens = _register_and_login(client, second)

    response = client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"username": first["username"]},
    )
    assert response.status_code == 400


def test_update_email_rejects_duplicate(client: TestClient) -> None:
    first = _unique_user()
    second = _unique_user()
    client.post("/auth/register", json=first)
    tokens = _register_and_login(client, second)

    response = client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"email": first["email"]},
    )
    assert response.status_code == 400


def test_update_profile_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    log_sink.clear()
    client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"full_name": "Test User"},
    )

    assert any(f"[UPDATE_PROFILE] user={payload['username']}" in msg for msg in log_sink)


def test_delete_profile_deactivates_account(client: TestClient) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    response = client.delete(
        "/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_deactivated_account_loses_access_immediately(client: TestClient) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    client.delete("/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})

    response = client.get(
        "/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 401


def test_deactivated_account_cannot_login_again(client: TestClient) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    client.delete("/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})

    response = client.post(
        "/auth/login", data={"username": payload["username"], "password": payload["password"]}
    )
    assert response.status_code == 401


def test_delete_profile_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    payload = _unique_user()
    tokens = _register_and_login(client, payload)

    log_sink.clear()
    client.delete("/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})

    assert any(f"[DEACTIVATE_ACCOUNT] user={payload['username']}" in msg for msg in log_sink)
