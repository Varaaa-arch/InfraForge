import uuid

from fastapi.testclient import TestClient


def _unique_user() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "password123",
    }


def test_register_and_login_flow(client: TestClient) -> None:
    payload = _unique_user()

    register_response = client.post("/auth/register", json=payload)
    assert register_response.status_code == 201
    register_body = register_response.json()
    assert register_body["success"] is True
    assert register_body["data"]["username"] == payload["username"]

    duplicate_response = client.post("/auth/register", json=payload)
    assert duplicate_response.status_code == 400
    duplicate_body = duplicate_response.json()
    assert duplicate_body["success"] is False
    assert duplicate_body["code"] == 400
    assert "message" in duplicate_body

    login_response = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()["data"]
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    me_response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["data"]["username"] == payload["username"]


def test_login_with_wrong_password_returns_401(client: TestClient) -> None:
    payload = _unique_user()
    client.post("/auth/register", json=payload)

    response = client.post(
        "/auth/login", data={"username": payload["username"], "password": "wrong-password"}
    )
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["code"] == 401


def test_me_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["success"] is False


def test_refresh_token_flow(client: TestClient) -> None:
    payload = _unique_user()
    client.post("/auth/register", json=payload)
    login_response = client.post(
        "/auth/login", data={"username": payload["username"], "password": payload["password"]}
    )
    refresh_token = login_response.json()["data"]["refresh_token"]

    refresh_response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 200
    assert "access_token" in refresh_response.json()["data"]


def test_refresh_token_cannot_be_used_as_access_token(client: TestClient) -> None:
    payload = _unique_user()
    client.post("/auth/register", json=payload)
    login_response = client.post(
        "/auth/login", data={"username": payload["username"], "password": payload["password"]}
    )
    refresh_token = login_response.json()["data"]["refresh_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert response.status_code == 401


def test_register_with_invalid_email_returns_consistent_error_shape(client: TestClient) -> None:
    payload = _unique_user()
    payload["email"] = "bukan-email-valid"

    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["code"] == 422
    assert "message" in body
