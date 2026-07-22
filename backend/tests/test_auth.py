import uuid

from fastapi.testclient import TestClient

from app.main import app
client = TestClient(app)

def _unique_username() -> dict:
    suffix = str(uuid.uuid4())[:8]
    return {
        "username": f"testuser_{suffix}",
        "email": f"testuser_{suffix}@example.com",
        "password": "testpassword",
    }

def test_register_and_login_flow() -> None:
    payload = _unique_username()

    register_response = client.post("/auth/register", json=payload)
    assert register_response.status_code == 201
    assert register_response.json()["username"] == payload["username"]

    duplicate_response = client.post("/auth/register", json=payload)
    assert duplicate_response.status_code == 400

    login_response = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    assert login_response.status_code == 200
    token = login_response.json()
    assert "access_token" in token
    assert "refresh_token" in token

    me_response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token['access_token']}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["username"] == payload["username"]

def test_login_with_wrong_password() -> None: 
    payload = _unique_username()
    client.post("/auth/register", json=payload)

    response = client.post(
        "/auth/login", data={"username": payload["username"], "password": "wrong-password"}
    )
    assert response.status_code == 401

def test_me_without_token() -> None:
    response = client.get("/auth/me")    
    assert response.status_code == 401

def test_refresh_token_flow() -> None:
    payload = _unique_username()
    client.post("/auth/register", json=payload)
    login_response = client.post(
        "/auth/login", data={"username": payload["username"], "password": payload["password"]}
    )
    refresh_token = login_response.json()["refresh_token"]
    refresh_response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 200
    assert "access_token" in refresh_response.json()

def test_refresh_token_cannot_be_used_as_access_token() -> None:
    payload = _unique_username()
    client.post("/auth/register", json=payload)
    login_response = client.post(
        "/auth/login", data={"username": payload["username"], "password": payload["password"]}
    )
    refresh_token = login_response.json()["refresh_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert response.status_code == 401
