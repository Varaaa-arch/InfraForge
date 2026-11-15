"""Test RBAC: peran user, matriks izin, dan endpoint manajemen user admin."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import roles
from app.core.roles import Permission, Role, has_permission
from app.models.user import User
from app.services import auth_service

PASSWORD = "password123"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _create_user(db: Session, *, role: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    username = f"rbac_{suffix}"
    return auth_service.create_user(
        db,
        username,
        f"{username}@example.com",
        PASSWORD,
        role=role,
    )


def _login(client: TestClient, username: str) -> str:
    response = client.post(
        "/auth/login", data={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["data"]["access_token"])


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _auth(client: TestClient, db: Session, role: str) -> tuple[User, dict[str, str]]:
    user = _create_user(db, role=role)
    return user, _headers(_login(client, user.username))


# ---------------------------------------------------------------------------
# Unit: matriks izin
# ---------------------------------------------------------------------------


def test_permission_matrix() -> None:
    assert has_permission(Role.ADMIN.value, Permission.USER_MANAGE)
    assert has_permission(Role.ADMIN.value, Permission.SERVER_WRITE)
    assert has_permission(Role.ADMIN.value, Permission.CONTAINER_DELETE)

    assert has_permission(Role.DEVELOPER.value, Permission.DEPLOY)
    assert has_permission(Role.DEVELOPER.value, Permission.ENV_VAR_WRITE)
    assert has_permission(Role.DEVELOPER.value, Permission.CONTAINER_LIFECYCLE)
    assert not has_permission(Role.DEVELOPER.value, Permission.USER_MANAGE)
    assert not has_permission(Role.DEVELOPER.value, Permission.SERVER_WRITE)
    assert not has_permission(Role.DEVELOPER.value, Permission.CONTAINER_DELETE)

    assert not has_permission(Role.VIEWER.value, Permission.PROJECT_WRITE)
    assert not has_permission(Role.VIEWER.value, Permission.DEPLOY)
    assert not has_permission("peran-tidak-dikenal", Permission.DEPLOY)
    assert not has_permission(None, Permission.DEPLOY)


# ---------------------------------------------------------------------------
# Registrasi & profil
# ---------------------------------------------------------------------------


def test_register_default_role_is_viewer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(roles, "DEFAULT_ROLE", Role.VIEWER.value)
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "username": f"new_{suffix}",
        "email": f"new_{suffix}@example.com",
        "password": PASSWORD,
    }

    register = client.post("/auth/register", json=payload)
    assert register.status_code == 201, register.text
    assert register.json()["data"]["role"] == "viewer"

    token = _login(client, payload["username"])
    me = client.get("/auth/me", headers=_headers(token))
    assert me.status_code == 200
    assert me.json()["data"]["role"] == "viewer"


def test_user_response_includes_role(client: TestClient, db_session: Session) -> None:
    user, headers = _auth(client, db_session, Role.DEVELOPER.value)
    response = client.get("/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "developer"
    assert response.json()["data"]["username"] == user.username


# ---------------------------------------------------------------------------
# Viewer: read-only
# ---------------------------------------------------------------------------


def test_viewer_can_read_but_cannot_mutate(
    client: TestClient, db_session: Session
) -> None:
    viewer, headers = _auth(client, db_session, Role.VIEWER.value)

    assert client.get("/projects", headers=headers).status_code == 200
    assert client.get("/servers", headers=headers).status_code == 200

    assert (
        client.post(
            "/projects", json={"name": "Viewer Project"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/servers", json={"name": "S", "host": "192.0.2.1"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/containers/apa-saja/start", headers=headers
        ).status_code
        == 403
    )


def test_viewer_cannot_reveal_env_var(
    client: TestClient, db_session: Session
) -> None:
    viewer, headers = _auth(client, db_session, Role.VIEWER.value)

    response = client.get("/projects/1/env/1", headers=headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Developer: operasional, bukan administrasi
# ---------------------------------------------------------------------------


def test_developer_can_manage_projects_and_env(
    client: TestClient, db_session: Session
) -> None:
    _, headers = _auth(client, db_session, Role.DEVELOPER.value)

    project = client.post(
        "/projects", json={"name": "Developer Project"}, headers=headers
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["data"]["id"]

    env = client.post(
        f"/projects/{project_id}/env",
        json={"env_vars": [{"key": "API_KEY", "value": "secret-value"}]},
        headers=headers,
    )
    assert env.status_code == 200, env.text


def test_developer_cannot_manage_users_or_servers(
    client: TestClient, db_session: Session
) -> None:
    _, headers = _auth(client, db_session, Role.DEVELOPER.value)

    assert client.get("/users", headers=headers).status_code == 403
    assert (
        client.post(
            "/servers", json={"name": "S", "host": "192.0.2.1"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/alert-channels",
            json={"name": "x", "type": "discord", "webhook_url": "https://x"},
            headers=headers,
        ).status_code
        == 403
    )


# ---------------------------------------------------------------------------
# Admin: manajemen user
# ---------------------------------------------------------------------------


def test_admin_can_list_and_update_users(
    client: TestClient, db_session: Session
) -> None:
    _, headers = _auth(client, db_session, Role.ADMIN.value)
    target = _create_user(db_session, role=Role.VIEWER.value)

    listing = client.get("/users", headers=headers)
    assert listing.status_code == 200
    usernames = [item["username"] for item in listing.json()["data"]]
    assert target.username in usernames

    updated = client.patch(
        f"/users/{target.id}", json={"role": "developer"}, headers=headers
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["role"] == "developer"


def test_admin_cannot_change_own_role(
    client: TestClient, db_session: Session
) -> None:
    admin, headers = _auth(client, db_session, Role.ADMIN.value)

    response = client.patch(
        f"/users/{admin.id}", json={"role": "viewer"}, headers=headers
    )
    assert response.status_code == 400


def test_deactivated_user_token_is_rejected(
    client: TestClient, db_session: Session
) -> None:
    _, admin_headers = _auth(client, db_session, Role.ADMIN.value)
    target = _create_user(db_session, role=Role.DEVELOPER.value)
    target_headers = _headers(_login(client, target.username))

    assert client.get("/auth/me", headers=target_headers).status_code == 200

    deactivated = client.patch(
        f"/users/{target.id}", json={"is_active": False}, headers=admin_headers
    )
    assert deactivated.status_code == 200, deactivated.text

    assert client.get("/auth/me", headers=target_headers).status_code == 401


def test_non_admin_role_payload_is_rejected(
    client: TestClient, db_session: Session
) -> None:
    _, headers = _auth(client, db_session, Role.ADMIN.value)
    target = _create_user(db_session, role=Role.VIEWER.value)

    response = client.patch(
        f"/users/{target.id}", json={"role": "superuser"}, headers=headers
    )
    assert response.status_code == 422


def test_update_unknown_user_returns_404(
    client: TestClient, db_session: Session
) -> None:
    _, headers = _auth(client, db_session, Role.ADMIN.value)
    response = client.patch(
        "/users/99999999", json={"role": "developer"}, headers=headers
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Label peran
# ---------------------------------------------------------------------------


def test_role_label() -> None:
    assert roles.role_label("admin") == "Admin"
    assert roles.role_label("developer") == "Developer"
    assert roles.role_label("viewer") == "Viewer"
    assert roles.role_label("lainnya") == "lainnya"
