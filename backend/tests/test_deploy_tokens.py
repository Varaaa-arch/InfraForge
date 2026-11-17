"""Test deployment token CI/CD: manajemen token, endpoint publik trigger, audit.

Semua interaksi Redis dan background deployment di-mock — tidak perlu Redis
nyata maupun eksekusi docker compose.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.middleware.audit_middleware import match_audit_rule
from app.models.user import User
from app.repositories import deployment_repository
from app.services import auth_service, deployment_token_service

PASSWORD = "password123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(db: Session, *, role: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    username = f"deptok_{suffix}"
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


def _create_project(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/projects",
        json={"name": f"proj-{uuid.uuid4().hex[:6]}", "description": "test"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return int(response.json()["data"]["id"])


def _create_server(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/servers",
        json={
            "name": f"server-{uuid.uuid4().hex[:6]}",
            "host": "192.168.1.10",
            "port": 22,
            "username": "ubuntu",
            "auth_type": "password",
            "password": "secret",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return int(response.json()["data"]["id"])


def _create_application(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    *,
    name: str | None = None,
    branch: str = "main",
) -> dict[str, object]:
    response = client.post(
        "/applications",
        json={
            "project_id": project_id,
            "name": name or f"app-{uuid.uuid4().hex[:6]}",
            "repository": "https://github.com/org/repo",
            "branch": branch,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["data"]


def _create_token(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    **overrides: object,
) -> dict[str, object]:
    body = {"name": "CI token", **overrides}
    response = client.post(
        f"/projects/{project_id}/deploy-tokens", json=body, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _trigger(
    client: TestClient, token: object, payload: dict[str, object] | None = None
) -> object:
    return client.post(f"/deploy/trigger/{token}", json=payload or {})


@pytest.fixture()
def queue_mocks() -> Generator[tuple[object, object], None, None]:
    """Mock Redis lock + background deployment untuk endpoint trigger."""
    with (
        patch("app.services.deployment_queue.redis_client") as redis_mock,
        patch(
            "app.services.deployment_queue.run_deployment_background"
        ) as background_mock,
    ):
        redis_mock.exists.return_value = 0
        redis_mock.get.return_value = None
        redis_mock.set.return_value = True
        redis_mock.delete.return_value = 1
        yield redis_mock, background_mock


def _setup_deployable(
    client: TestClient, db_session: Session
) -> tuple[User, dict[str, str], int, int, dict[str, object]]:
    user = _create_user(db_session, role=Role.ADMIN.value)
    headers = _login(client, user.username)
    project_id = _create_project(client, headers)
    server_id = _create_server(client, headers)
    app = _create_application(client, headers, project_id)
    return user, headers, project_id, server_id, app


# ---------------------------------------------------------------------------
# Manajemen token
# ---------------------------------------------------------------------------

def test_create_token_returns_plaintext_once_and_stores_hash(
    client: TestClient, db_session: Session
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )

    data = _create_token(client, headers, project_id, expires_in_days=7)
    token = str(data["token"])

    assert token.startswith("dt_")
    assert token.count("_") == 2
    assert data["prefix"] == "_".join(token.split("_")[:2])
    assert data["project_id"] == project_id
    assert data["name"] == "CI token"
    assert data["expires_at"] is not None

    record = deployment_token_service.find_active_by_token(db_session, token)
    assert record is not None
    assert record.token_hash == deployment_token_service.hash_token(token)
    assert record.token_hash != token
    assert len(record.token_hash) == 64

    listing = client.get(
        f"/projects/{project_id}/deploy-tokens", headers=headers
    )
    assert listing.status_code == 200
    items = listing.json()["data"]
    assert len(items) == 1
    assert items[0]["prefix"] == data["prefix"]
    assert "token" not in items[0]
    assert "token_hash" not in items[0]


def test_non_owner_cannot_manage_tokens(
    client: TestClient, db_session: Session
) -> None:
    _owner, _owner_headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    other = _create_user(db_session, role=Role.ADMIN.value)
    other_headers = _login(client, other.username)

    assert (
        client.get(
            f"/projects/{project_id}/deploy-tokens", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/projects/{project_id}/deploy-tokens",
            json={"name": "nope"},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/projects/{project_id}/deploy-tokens/1", headers=other_headers
        ).status_code
        == 404
    )


def test_viewer_cannot_create_token(
    client: TestClient, db_session: Session
) -> None:
    _user, admin_headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    viewer = _create_user(db_session, role=Role.VIEWER.value)
    viewer_headers = _login(client, viewer.username)

    response = client.post(
        f"/projects/{project_id}/deploy-tokens",
        json={"name": "viewer token"},
        headers=viewer_headers,
    )
    assert response.status_code == 403


def test_developer_can_create_own_project_token(
    client: TestClient, db_session: Session
) -> None:
    developer = _create_user(db_session, role=Role.DEVELOPER.value)
    headers = _login(client, developer.username)
    project_id = _create_project(client, headers)

    _create_token(client, headers, project_id)


# ---------------------------------------------------------------------------
# Endpoint publik trigger
# ---------------------------------------------------------------------------

def test_trigger_success_single_application(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _redis, background_mock = queue_mocks
    _user, headers, project_id, server_id, app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    response = _trigger(client, data["token"])
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["application_id"] == app["id"]
    assert body["application_name"] == app["name"]
    assert body["branch"] == "main"
    assert body["status"] == "pending"
    assert body["deployment_id"] > 0

    deployment = deployment_repository.get_by_id(db_session, body["deployment_id"])
    assert deployment is not None
    assert deployment.trigger_source == "ci_token"
    assert deployment.branch == "main"
    assert deployment.server_id == server_id
    assert deployment.status.value == "pending"

    background_mock.assert_called_once_with(
        deployment_id=body["deployment_id"],
        application_id=app["id"],
        server_id=server_id,
    )

    listing = client.get(
        f"/projects/{project_id}/deploy-tokens", headers=headers
    ).json()["data"]
    assert listing[0]["last_used_at"] is not None


def test_trigger_branch_override(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    response = _trigger(client, data["token"], {"branch": "release/1.0"})
    assert response.status_code == 202, response.text
    assert response.json()["data"]["branch"] == "release/1.0"

    deployment = deployment_repository.get_by_id(
        db_session, response.json()["data"]["deployment_id"]
    )
    assert deployment is not None
    assert deployment.branch == "release/1.0"


def test_trigger_multi_application_requires_application_id(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    first = _create_application(client, headers, project_id, name="api")
    _create_application(client, headers, project_id, name="worker")
    data = _create_token(client, headers, project_id)

    ambiguous = _trigger(client, data["token"])
    assert ambiguous.status_code == 422
    assert "application_id" in ambiguous.json()["message"]

    explicit = _trigger(client, data["token"], {"application_id": first["id"]})
    assert explicit.status_code == 202, explicit.text
    assert explicit.json()["data"]["application_name"] == "api"


def test_trigger_rejects_foreign_application_id(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    other_project = _create_project(client, headers)
    foreign_app = _create_application(client, headers, other_project)
    data = _create_token(client, headers, project_id)

    response = _trigger(
        client, data["token"], {"application_id": foreign_app["id"]}
    )
    assert response.status_code == 422


def test_trigger_invalid_revoked_and_expired_tokens(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    _create_token(client, headers, project_id)

    assert _trigger(client, "dt_deadbeef_" + "0" * 64).status_code == 404

    revoked = _create_token(client, headers, project_id, name="revoked")
    revoke_response = client.delete(
        f"/projects/{project_id}/deploy-tokens/{revoked['id']}",
        headers=headers,
    )
    assert revoke_response.status_code == 200
    assert _trigger(client, revoked["token"]).status_code == 404

    expired = _create_token(client, headers, project_id, name="expired")
    record = deployment_token_service.find_active_by_token(
        db_session, str(expired["token"])
    )
    assert record is not None
    record.expires_at = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
    db_session.add(record)
    db_session.commit()
    assert _trigger(client, expired["token"]).status_code == 404


def test_trigger_conflict_when_deployment_running(
    client: TestClient,
    db_session: Session,
    queue_mocks: tuple[object, object],
) -> None:
    redis_mock, background_mock = queue_mocks
    redis_mock.get.return_value = "42"
    _user, headers, project_id, _server_id, app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    response = _trigger(client, data["token"])
    assert response.status_code == 409
    assert "42" in response.json()["message"]
    assert (
        deployment_repository.list_by_application(db_session, int(app["id"])) == []
    )
    background_mock.assert_not_called()


def test_trigger_requires_application_and_server(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    user = _create_user(db_session, role=Role.ADMIN.value)
    headers = _login(client, user.username)
    project_id = _create_project(client, headers)
    data = _create_token(client, headers, project_id)

    empty_project = _trigger(client, data["token"])
    assert empty_project.status_code == 422
    assert "belum memiliki aplikasi" in empty_project.json()["message"]

    _create_application(client, headers, project_id)
    no_server = _trigger(client, data["token"])
    assert no_server.status_code == 422
    assert "server" in no_server.json()["message"].lower()


def test_trigger_rejects_foreign_server(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    other = _create_user(db_session, role=Role.ADMIN.value)
    other_headers = _login(client, other.username)
    foreign_server_id = _create_server(client, other_headers)

    response = _trigger(client, data["token"], {"server_id": foreign_server_id})
    assert response.status_code == 422
    assert str(foreign_server_id) in response.json()["message"]


# ---------------------------------------------------------------------------
# Riwayat deployment & trigger source
# ---------------------------------------------------------------------------

def test_list_deployments_filtered_by_project(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    other_project = _create_project(client, headers)
    _create_application(client, headers, other_project)

    first_token = _create_token(client, headers, project_id, name="p1")
    second_token = _create_token(client, headers, other_project, name="p2")
    first_trigger = _trigger(client, first_token["token"])
    _trigger(client, second_token["token"])
    assert first_trigger.status_code == 202

    response = client.get(
        f"/deployments?project_id={project_id}", headers=headers
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["application_id"] == _app["id"]
    assert items[0]["trigger_source"] == "ci_token"

    other = _create_user(db_session, role=Role.ADMIN.value)
    other_headers = _login(client, other.username)
    assert (
        client.get(
            f"/deployments?project_id={project_id}", headers=other_headers
        ).status_code
        == 404
    )


def test_deployment_repository_trigger_source_defaults_to_manual(
    client: TestClient, db_session: Session
) -> None:
    _user, headers, _project_id, server_id, app = _setup_deployable(
        client, db_session
    )

    manual = deployment_repository.create(
        db_session, int(app["id"]), server_id, "main"
    )
    webhook = deployment_repository.create(
        db_session,
        int(app["id"]),
        server_id,
        "main",
        trigger_source="github_webhook",
    )
    assert manual.trigger_source == "manual"
    assert webhook.trigger_source == "github_webhook"


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def test_audit_rules_cover_token_management_and_trigger() -> None:
    create_rule = match_audit_rule("POST", "/projects/7/deploy-tokens")
    assert create_rule is not None
    assert create_rule[0].action == "DEPLOY_TOKEN_CREATE"
    assert create_rule[1] == {"project_id": "7"}

    revoke_rule = match_audit_rule("DELETE", "/projects/7/deploy-tokens/3")
    assert revoke_rule is not None
    assert revoke_rule[0].action == "DEPLOY_TOKEN_REVOKE"
    assert revoke_rule[1] == {"project_id": "7", "id": "3"}

    trigger_rule = match_audit_rule("POST", "/deploy/trigger/dt_abc_secret")
    assert trigger_rule is not None
    assert trigger_rule[0].action == "DEPLOY_TRIGGER"
    assert trigger_rule[1] == {}


def test_trigger_audit_event_uses_token_name_and_id(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id, name="gh-actions")

    with patch("app.services.audit_service.record") as record_mock:
        response = _trigger(client, data["token"])
    assert response.status_code == 202

    recorded = [call.args[0] for call in record_mock.call_args_list]
    events = [event for event in recorded if event.action == "DEPLOY_TRIGGER"]
    assert len(events) == 1

    event = events[0]
    assert event.username == "deploy-token:gh-actions"
    assert event.resource_type == "deploy_token"
    assert event.resource_id == str(data["id"])
    assert event.details["application_id"] == str(app["id"])
    assert event.details["branch"] == "main"
    assert event.path == "/deploy/trigger/[redacted]"
    assert "dt_" not in event.username
    assert str(data["token"]) not in str(event.details)

    invalid_token = "dt_deadbeef_" + "x" * 64
    with patch("app.services.audit_service.record") as record_mock:
        response = _trigger(client, invalid_token)
    assert response.status_code == 404

    recorded = [call.args[0] for call in record_mock.call_args_list]
    events = [event for event in recorded if event.action == "DEPLOY_TRIGGER"]
    assert len(events) == 1
    assert events[0].path == "/deploy/trigger/[redacted]"
    assert invalid_token not in events[0].path
    assert invalid_token not in str(events[0].details)
