"""Test audit log persisten: aturan allowlist, middleware, dan service writer."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.middleware.audit_middleware import match_audit_rule
from app.services import audit_service, auth_service


# ---------------------------------------------------------------------------
# Allowlist aturan audit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "action"),
    [
        ("POST", "/projects", "PROJECT_CREATE"),
        ("PATCH", "/projects/7", "PROJECT_UPDATE"),
        ("PATCH", "/projects/7/repository", "PROJECT_REPOSITORY_UPDATE"),
        ("DELETE", "/projects/7", "PROJECT_DELETE"),
        ("POST", "/projects/7/env", "ENV_VAR_BULK_UPSERT"),
        ("GET", "/projects/7/env/3", "ENV_VAR_REVEAL"),
        ("PATCH", "/projects/7/env/3", "ENV_VAR_UPDATE"),
        ("DELETE", "/projects/7/env/3", "ENV_VAR_DELETE"),
        ("POST", "/servers", "SERVER_CREATE"),
        ("DELETE", "/servers/2", "SERVER_DELETE"),
        ("POST", "/applications", "APPLICATION_CREATE"),
        ("POST", "/docker/images/pull", "IMAGE_PULL"),
        ("DELETE", "/docker/images/alpine:3.20", "IMAGE_DELETE"),
        ("POST", "/containers/my-app/start", "CONTAINER_START"),
        ("POST", "/containers/my-app/stop", "CONTAINER_STOP"),
        ("POST", "/containers/my-app/restart", "CONTAINER_RESTART"),
        ("DELETE", "/containers/my-app", "CONTAINER_DELETE"),
        ("POST", "/deployments", "DEPLOY"),
        ("POST", "/deployments/11/rollback", "ROLLBACK"),
        ("POST", "/deployments/11/health-check", "DEPLOY_HEALTH_CHECK"),
        ("POST", "/alert-channels", "ALERT_CHANNEL_CREATE"),
        ("PATCH", "/alert-channels/2", "ALERT_CHANNEL_UPDATE"),
        ("DELETE", "/alert-channels/2", "ALERT_CHANNEL_DELETE"),
        ("POST", "/alert-channels/2/test", "ALERT_CHANNEL_TEST"),
        ("POST", "/auth/login", "AUTH_LOGIN"),
        ("POST", "/auth/register", "AUTH_REGISTER"),
        ("POST", "/auth/logout", "AUTH_LOGOUT"),
        ("POST", "/auth/change-password", "PASSWORD_CHANGE"),
        ("PATCH", "/users/5", "UPDATE_USER"),
        ("POST", "/webhooks/github", "WEBHOOK_GITHUB"),
    ],
)
def test_rules_match_mutations(method: str, path: str, action: str) -> None:
    matched = match_audit_rule(method, path)
    assert matched is not None
    rule, _ = matched
    assert rule.action == action


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/projects"),
        ("GET", "/projects/7"),
        ("GET", "/projects/7/env"),
        ("GET", "/servers"),
        ("GET", "/containers"),
        ("GET", "/deployments"),
        ("GET", "/alert-channels"),
        ("GET", "/users"),
        ("GET", "/users/me"),
        ("GET", "/metrics"),
        ("POST", "/auth/refresh"),
        ("POST", "/unknown"),
        ("PUT", "/projects/7"),
    ],
)
def test_rules_ignore_non_audited_requests(method: str, path: str) -> None:
    assert match_audit_rule(method, path) is None


def test_rules_capture_resource_groups() -> None:
    matched = match_audit_rule("PATCH", "/projects/7/env/3")
    assert matched is not None
    _, groups = matched
    assert groups == {"project_id": "7", "id": "3"}

    matched = match_audit_rule("POST", "/containers/my-app/restart")
    assert matched is not None
    _, groups = matched
    assert groups == {"id": "my-app"}


def test_rules_accept_trailing_slash() -> None:
    matched = match_audit_rule("POST", "/projects/")
    assert matched is not None
    assert matched[0].action == "PROJECT_CREATE"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.events: list[audit_service.AuditEvent] = []

    def __call__(
        self, event: audit_service.AuditEvent, *, db: Session | None = None
    ) -> None:
        self.events.append(event)

    def by_action(self, action: str) -> list[audit_service.AuditEvent]:
        return [event for event in self.events if event.action == action]


def _unique_user() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"audit_{suffix}",
        "email": f"audit_{suffix}@example.com",
        "password": "password123",
    }


def _login(client: TestClient, username: str, password: str = "password123") -> str:
    response = client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["data"]["access_token"])


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def test_middleware_records_register(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(audit_service, "record", recorder)

    payload = _unique_user()
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201

    events = recorder.by_action("AUTH_REGISTER")
    assert len(events) == 1
    event = events[0]
    assert event.username == payload["username"]
    assert event.method == "POST"
    assert event.path == "/auth/register"
    assert event.status_code == 201
    assert event.resource_type == "user"
    assert event.user_id is not None


def test_middleware_records_successful_mutation_with_user(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(audit_service, "record", recorder)

    payload = _unique_user()
    client.post("/auth/register", json=payload)
    token = _login(client, payload["username"])
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/projects", json={"name": "Audit Project"}, headers=headers
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["data"]["id"]

    created = recorder.by_action("PROJECT_CREATE")
    assert len(created) == 1
    assert created[0].username == payload["username"]
    assert created[0].status_code == 201
    assert created[0].resource_type == "project"
    assert created[0].ip_address is not None

    updated = client.patch(
        f"/projects/{project_id}",
        json={"description": "Diubah"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text

    events = recorder.by_action("PROJECT_UPDATE")
    assert len(events) == 1
    assert events[0].resource_id == str(project_id)
    assert events[0].details == {}


def test_middleware_records_rejected_mutation(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(audit_service, "record", recorder)

    suffix = uuid.uuid4().hex[:8]
    username = f"viewer_{suffix}"
    auth_service.create_user(
        db_session,
        username,
        f"{username}@example.com",
        "password123",
        role=Role.VIEWER.value,
    )
    token = _login(client, username)

    response = client.post(
        "/projects",
        json={"name": "Ditolak"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403

    events = recorder.by_action("PROJECT_CREATE")
    assert len(events) == 1
    assert events[0].username == username
    assert events[0].status_code == 403


def test_middleware_does_not_record_reads(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(audit_service, "record", recorder)

    payload = _unique_user()
    client.post("/auth/register", json=payload)
    token = _login(client, payload["username"])

    assert (
        client.get(
            "/projects", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 200
    )

    assert recorder.by_action("PROJECT_CREATE") == []
    assert all(event.method != "GET" for event in recorder.events)


def test_middleware_logs_invalid_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(audit_service, "record", recorder)

    response = client.post(
        "/auth/login", data={"username": "tidak-ada", "password": "salah"}
    )
    assert response.status_code == 401

    events = recorder.by_action("AUTH_LOGIN")
    assert len(events) == 1
    assert events[0].username == "tidak-ada"
    assert events[0].status_code == 401


def test_audit_write_failure_does_not_break_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(
        event: audit_service.AuditEvent, *, db: Session | None = None
    ) -> None:
        raise RuntimeError("database audit down")

    monkeypatch.setattr(audit_service, "record", _boom)

    response = client.post("/auth/register", json=_unique_user())
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Service writer
# ---------------------------------------------------------------------------


def test_service_persists_event(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models.audit_log import AuditLog

    monkeypatch.setattr(audit_service, "AUDIT_PERSIST_ENABLED", True)

    suffix = uuid.uuid4().hex[:8]
    user = auth_service.create_user(
        db_session,
        f"writer_{suffix}",
        f"writer_{suffix}@example.com",
        "password123",
        role=Role.DEVELOPER.value,
    )

    event = audit_service.AuditEvent(
        action="DEPLOY",
        method="POST",
        path="/deployments",
        status_code=201,
        user_id=user.id,
        username=user.username,
        resource_type="deployment",
        resource_id="42",
        ip_address="192.0.2.5",
        user_agent="pytest-agent",
        details={"branch": "main"},
    )
    entry = audit_service.record(event, db=db_session)

    assert entry is not None
    assert entry.action == "DEPLOY"
    assert entry.username == user.username
    assert entry.details == {"branch": "main"}
    assert entry.created_at is not None

    fetched = db_session.query(AuditLog).filter(AuditLog.id == entry.id).one()
    assert fetched.path == "/deployments"
    assert fetched.status_code == 201
    assert fetched.ip_address == "192.0.2.5"


def test_service_respects_disabled_switch(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit_service, "AUDIT_PERSIST_ENABLED", False)

    event = audit_service.AuditEvent(
        action="DEPLOY", method="POST", path="/deployments", status_code=201
    )
    assert audit_service.record(event, db=db_session) is None


def test_service_swallows_write_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_service, "AUDIT_PERSIST_ENABLED", True)

    class _BrokenSession:
        def add(self, obj: Any) -> None:
            raise RuntimeError("boom")

        def rollback(self) -> None:
            pass

    event = audit_service.AuditEvent(
        action="DEPLOY", method="POST", path="/deployments", status_code=201
    )
    result = audit_service.record(event, db=_BrokenSession())  # type: ignore[arg-type]
    assert result is None
