"""Test Personal Access Token (PAT): pembuatan, autentikasi, scope, dan cabut."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models.user import User
from app.services import api_token_service, auth_service

PASSWORD = "password123"


def _create_user(db: Session, *, role: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    username = f"pat_{suffix}"
    return auth_service.create_user(
        db,
        username,
        f"{username}@example.com",
        PASSWORD,
        role=role,
    )


def _login(client: TestClient, username: str) -> dict[str, str]:
    response = client.post(
        "/auth/login", data={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _create_token(
    client: TestClient,
    headers: dict[str, str],
    **payload: object,
) -> dict[str, object]:
    body = {"name": "CI token", **payload}
    response = client.post("/api-tokens", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _pat_headers(token: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_token_returns_plaintext_once_and_stores_hash(
    client: TestClient, db_session: Session
) -> None:
    user = _create_user(db_session, role=Role.DEVELOPER.value)
    headers = _login(client, user.username)

    data = _create_token(client, headers)
    token = str(data["token"])

    assert token.startswith("if_")
    assert token.count("_") == 2
    assert data["prefix"] == "_".join(token.split("_")[:2])
    assert data["name"] == "CI token"
    assert data["scopes"] is None
    assert data["revoked_at"] is None

    record = api_token_service.find_active_by_token(db_session, token)
    assert record is not None
    assert record.token_hash == api_token_service.hash_token(token)
    assert record.token_hash != token
    assert len(record.token_hash) == 64

    listing = client.get("/api-tokens", headers=headers)
    assert listing.status_code == 200
    items = listing.json()["data"]
    assert len(items) == 1
    assert "token" not in items[0]
    assert "token_hash" not in items[0]
    assert items[0]["prefix"] == data["prefix"]


def test_pat_can_authenticate(client: TestClient, db_session: Session) -> None:
    user = _create_user(db_session, role=Role.DEVELOPER.value)
    data = _create_token(client, _login(client, user.username))

    response = client.get("/auth/me", headers=_pat_headers(data["token"]))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["username"] == user.username
    assert client.get("/projects", headers=_pat_headers(data["token"])).status_code == 200


def test_pat_write_respects_role(
    client: TestClient, db_session: Session
) -> None:
    viewer = _create_user(db_session, role=Role.VIEWER.value)
    viewer_pat = _create_token(client, _login(client, viewer.username))["token"]

    denied = client.post(
        "/projects",
        json={"name": f"pat-viewer-{uuid.uuid4().hex[:6]}"},
        headers=_pat_headers(viewer_pat),
    )
    assert denied.status_code == 403

    developer = _create_user(db_session, role=Role.DEVELOPER.value)
    dev_pat = _create_token(client, _login(client, developer.username))["token"]

    allowed = client.post(
        "/projects",
        json={"name": f"pat-dev-{uuid.uuid4().hex[:6]}"},
        headers=_pat_headers(dev_pat),
    )
    assert allowed.status_code == 201, allowed.text


def test_read_only_scope_blocks_write(
    client: TestClient, db_session: Session
) -> None:
    user = _create_user(db_session, role=Role.DEVELOPER.value)
    headers = _login(client, user.username)
    data = _create_token(client, headers, scopes=["read"])

    assert data["scopes"] == ["read"]
    pat = _pat_headers(data["token"])
    assert client.get("/projects", headers=pat).status_code == 200

    response = client.post(
        "/projects",
        json={"name": f"pat-ro-{uuid.uuid4().hex[:6]}"},
        headers=pat,
    )
    assert response.status_code == 403
    assert "akses baca" in response.json()["message"]


def test_revoke_token(client: TestClient, db_session: Session) -> None:
    user = _create_user(db_session, role=Role.DEVELOPER.value)
    headers = _login(client, user.username)
    data = _create_token(client, headers)
    pat = _pat_headers(data["token"])

    assert client.get("/auth/me", headers=pat).status_code == 200

    response = client.delete(f"/api-tokens/{data['id']}", headers=headers)
    assert response.status_code == 200, response.text

    assert client.get("/auth/me", headers=pat).status_code == 401

    again = client.delete(f"/api-tokens/{data['id']}", headers=headers)
    assert again.status_code == 200

    items = client.get("/api-tokens", headers=headers).json()["data"]
    assert items[0]["revoked_at"] is not None


def test_revoke_other_users_token_not_found(
    client: TestClient, db_session: Session
) -> None:
    owner = _create_user(db_session, role=Role.DEVELOPER.value)
    other = _create_user(db_session, role=Role.ADMIN.value)
    data = _create_token(client, _login(client, owner.username))

    response = client.delete(
        f"/api-tokens/{data['id']}", headers=_login(client, other.username)
    )
    assert response.status_code == 404


def test_expired_token_rejected(
    client: TestClient, db_session: Session
) -> None:
    user = _create_user(db_session, role=Role.DEVELOPER.value)
    data = _create_token(client, _login(client, user.username))

    record = api_token_service.find_active_by_token(db_session, str(data["token"]))
    assert record is not None
    record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.add(record)
    db_session.commit()

    response = client.get("/auth/me", headers=_pat_headers(data["token"]))
    assert response.status_code == 401


def test_inactive_user_token_rejected(
    client: TestClient, db_session: Session
) -> None:
    user = _create_user(db_session, role=Role.DEVELOPER.value)
    data = _create_token(client, _login(client, user.username))

    user.is_active = False
    db_session.add(user)
    db_session.commit()

    response = client.get("/auth/me", headers=_pat_headers(data["token"]))
    assert response.status_code == 401


def test_last_used_at_updated(
    client: TestClient, db_session: Session
) -> None:
    user = _create_user(db_session, role=Role.DEVELOPER.value)
    data = _create_token(client, _login(client, user.username))

    assert client.get("/auth/me", headers=_pat_headers(data["token"])).status_code == 200

    record = api_token_service.find_active_by_token(db_session, str(data["token"]))
    assert record is not None
    assert record.last_used_at is not None


def test_create_token_validation(
    client: TestClient, db_session: Session
) -> None:
    user = _create_user(db_session, role=Role.DEVELOPER.value)
    headers = _login(client, user.username)

    assert (
        client.post("/api-tokens", json={"name": ""}, headers=headers).status_code
        == 422
    )
    assert (
        client.post(
            "/api-tokens", json={"name": "x", "expires_in_days": 400}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api-tokens", json={"name": "x", "scopes": ["admin"]}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api-tokens", json={"name": "x", "scopes": []}, headers=headers
        ).status_code
        == 422
    )


def test_token_requires_auth(client: TestClient) -> None:
    assert client.get("/api-tokens").status_code == 401
    assert client.post("/api-tokens", json={"name": "x"}).status_code == 401
