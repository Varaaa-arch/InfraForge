"""Test API audit log: cakupan per peran, filter, dan metadata."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models.user import User
from app.repositories import audit_repository
from app.services import auth_service

PASSWORD = "password123"


def _create_user(db: Session, *, role: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    username = f"auditapi_{suffix}"
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


def _entry(
    db: Session,
    *,
    username: str,
    action: str = "DEPLOY",
    user_id: int | None = None,
    created_at: datetime | None = None,
) -> None:
    entry = audit_repository.create(
        db,
        action=action,
        method="POST",
        path="/deployments",
        status_code=201,
        user_id=user_id,
        username=username,
        resource_type="deployment",
        resource_id="1",
        details={"source": "test"},
    )
    if created_at is not None:
        entry.created_at = created_at
        db.add(entry)
        db.commit()


def test_requires_auth(client: TestClient) -> None:
    assert client.get("/audit-logs").status_code == 401
    assert client.get("/audit-logs/filters").status_code == 401


def test_admin_sees_all_entries(client: TestClient, db_session: Session) -> None:
    admin = _create_user(db_session, role=Role.ADMIN.value)
    viewer = _create_user(db_session, role=Role.VIEWER.value)
    _entry(db_session, username=admin.username, action="SERVER_CREATE")
    _entry(db_session, username=viewer.username)
    _entry(db_session, username=viewer.username, action="ROLLBACK")

    response = client.get("/audit-logs", headers=_login(client, admin.username))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert {item["username"] for item in data["items"]} == {
        admin.username,
        viewer.username,
    }


def test_non_admin_sees_only_own_entries(
    client: TestClient, db_session: Session
) -> None:
    viewer = _create_user(db_session, role=Role.VIEWER.value)
    other = _create_user(db_session, role=Role.DEVELOPER.value)
    _entry(db_session, username=viewer.username)
    _entry(db_session, username=other.username, action="ROLLBACK")

    response = client.get("/audit-logs", headers=_login(client, viewer.username))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["username"] == viewer.username


def test_non_admin_cannot_filter_other_user(
    client: TestClient, db_session: Session
) -> None:
    viewer = _create_user(db_session, role=Role.VIEWER.value)
    other = _create_user(db_session, role=Role.DEVELOPER.value)

    response = client.get(
        f"/audit-logs?username={other.username}",
        headers=_login(client, viewer.username),
    )
    assert response.status_code == 403


def test_filter_by_action(client: TestClient, db_session: Session) -> None:
    admin = _create_user(db_session, role=Role.ADMIN.value)
    _entry(db_session, username=admin.username, action="DEPLOY")
    _entry(db_session, username=admin.username, action="ROLLBACK")

    response = client.get(
        "/audit-logs?action=ROLLBACK", headers=_login(client, admin.username)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["action"] == "ROLLBACK"


def test_filter_by_username(client: TestClient, db_session: Session) -> None:
    admin = _create_user(db_session, role=Role.ADMIN.value)
    developer = _create_user(db_session, role=Role.DEVELOPER.value)
    _entry(db_session, username=admin.username)
    _entry(db_session, username=developer.username)

    response = client.get(
        f"/audit-logs?username={developer.username}",
        headers=_login(client, admin.username),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["username"] == developer.username


def test_filter_by_date_range(client: TestClient, db_session: Session) -> None:
    admin = _create_user(db_session, role=Role.ADMIN.value)
    now = datetime.now(timezone.utc)
    _entry(db_session, username=admin.username, action="OLD", created_at=now - timedelta(days=10))
    _entry(db_session, username=admin.username, action="NEW", created_at=now - timedelta(hours=1))

    date_from = (now - timedelta(days=1)).isoformat()
    date_to = now.isoformat()
    response = client.get(
        "/audit-logs",
        params={"from": date_from, "to": date_to},
        headers=_login(client, admin.username),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["action"] == "NEW"


def test_pagination(client: TestClient, db_session: Session) -> None:
    admin = _create_user(db_session, role=Role.ADMIN.value)
    for index in range(3):
        _entry(db_session, username=admin.username, action=f"ACT_{index}")

    response = client.get(
        "/audit-logs?limit=1&offset=1", headers=_login(client, admin.username)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 3
    assert data["limit"] == 1
    assert data["offset"] == 1
    assert len(data["items"]) == 1


def test_filters_meta_admin(client: TestClient, db_session: Session) -> None:
    admin = _create_user(db_session, role=Role.ADMIN.value)
    _entry(db_session, username=admin.username, action="DEPLOY")

    response = client.get(
        "/audit-logs/filters", headers=_login(client, admin.username)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_admin"] is True
    assert "DEPLOY" in data["actions"]
    assert admin.username in data["usernames"]


def test_filters_meta_non_admin(client: TestClient, db_session: Session) -> None:
    viewer = _create_user(db_session, role=Role.VIEWER.value)
    other = _create_user(db_session, role=Role.DEVELOPER.value)
    _entry(db_session, username=other.username, action="ROLLBACK")

    response = client.get(
        "/audit-logs/filters", headers=_login(client, viewer.username)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_admin"] is False
    assert data["usernames"] == [viewer.username]
    assert "ROLLBACK" in data["actions"]


def test_unknown_action_returns_empty(client: TestClient, db_session: Session) -> None:
    admin = _create_user(db_session, role=Role.ADMIN.value)
    _entry(db_session, username=admin.username)

    response = client.get(
        "/audit-logs?action=TIDAK_ADA", headers=_login(client, admin.username)
    )
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 0
    assert response.json()["data"]["items"] == []
