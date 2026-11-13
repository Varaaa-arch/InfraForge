import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alert import AlertStatus
from app.repositories import (
    alert_repository,
    application_repository,
    deployment_repository,
)
from app.schemas.application import ApplicationCreate
from app.services import container_service


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
    return dict(login_response.json()["data"])


def _auth_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _patch_containers(
    monkeypatch: pytest.MonkeyPatch, running: int = 0, stopped: int = 0
) -> None:
    containers = [
        container_service.ContainerInfo(
            id=f"run{i}", name=f"run{i}", image="img", status="running", created=""
        )
        for i in range(running)
    ]
    containers += [
        container_service.ContainerInfo(
            id=f"stop{i}", name=f"stop{i}", image="img", status="exited", created=""
        )
        for i in range(stopped)
    ]
    monkeypatch.setattr(
        container_service, "list_containers", lambda **_kwargs: containers
    )


def _create_project(client: TestClient, tokens: dict[str, str], name: str) -> int:
    response = client.post(
        "/projects", headers=_auth_header(tokens), json={"name": name}
    )
    return int(response.json()["data"]["id"])


def test_dashboard_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/dashboard")
    assert response.status_code == 401


def test_dashboard_with_no_projects(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_containers(monkeypatch)
    tokens = _register_and_login(client, _unique_user())

    response = client.get("/dashboard", headers=_auth_header(tokens))
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["projects"] == 0
    assert body["applications"] == 0
    assert body["deployments"] == 0
    assert body["containers"] == 0
    assert body["containers_total"] == 0
    assert body["servers"] == 0
    assert body["servers_active"] == 0
    assert body["servers_inactive"] == 0
    assert body["servers_error"] == 0
    assert body["alerts_active"] == 0
    assert body["alerts_critical"] == 0
    assert body["alerts_warning"] == 0
    assert body["alerts_info"] == 0
    assert body["generated_at"]


def test_dashboard_counts_owned_projects(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    for i in range(3):
        client.post("/projects", headers=_auth_header(tokens), json={"name": f"Project {i}"})

    response = client.get("/dashboard", headers=_auth_header(tokens))
    assert response.json()["data"]["projects"] == 3


def test_dashboard_only_counts_own_projects_not_others(client: TestClient) -> None:
    tokens_a = _register_and_login(client, _unique_user())
    tokens_b = _register_and_login(client, _unique_user())

    client.post("/projects", headers=_auth_header(tokens_a), json={"name": "A1"})
    client.post("/projects", headers=_auth_header(tokens_a), json={"name": "A2"})
    client.post("/projects", headers=_auth_header(tokens_b), json={"name": "B1"})

    response_a = client.get("/dashboard", headers=_auth_header(tokens_a))
    response_b = client.get("/dashboard", headers=_auth_header(tokens_b))

    assert response_a.json()["data"]["projects"] == 2
    assert response_b.json()["data"]["projects"] == 1


def test_dashboard_count_decreases_after_delete(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    create_response = client.post(
        "/projects", headers=_auth_header(tokens), json={"name": "Temp Project"}
    )
    project_id = create_response.json()["data"]["id"]

    client.delete(f"/projects/{project_id}", headers=_auth_header(tokens))

    response = client.get("/dashboard", headers=_auth_header(tokens))
    assert response.json()["data"]["projects"] == 0


def test_dashboard_counts_owned_servers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_containers(monkeypatch)
    tokens_a = _register_and_login(client, _unique_user())
    tokens_b = _register_and_login(client, _unique_user())

    for i in range(2):
        client.post(
            "/servers",
            headers=_auth_header(tokens_a),
            json={
                "name": f"server-a-{i}",
                "host": f"10.0.0.{i + 1}",
                "username": "ubuntu",
                "auth_type": "password",
                "password": "secret123",
            },
        )
    client.post(
        "/servers",
        headers=_auth_header(tokens_b),
        json={
            "name": "server-b",
            "host": "10.0.0.10",
            "username": "ubuntu",
            "auth_type": "password",
            "password": "secret123",
        },
    )

    response_a = client.get("/dashboard", headers=_auth_header(tokens_a))
    response_b = client.get("/dashboard", headers=_auth_header(tokens_b))

    assert response_a.json()["data"]["servers"] == 2
    assert response_a.json()["data"]["servers_inactive"] == 2
    assert response_b.json()["data"]["servers"] == 1


def test_dashboard_counts_deployments(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_containers(monkeypatch)
    tokens_a = _register_and_login(client, _unique_user())
    tokens_b = _register_and_login(client, _unique_user())

    project_a = _create_project(client, tokens_a, "Deploy Project A")
    project_b = _create_project(client, tokens_b, "Deploy Project B")

    app_a = application_repository.create(
        db_session, ApplicationCreate(project_id=project_a, name="api-a")
    )
    app_b = application_repository.create(
        db_session, ApplicationCreate(project_id=project_b, name="api-b")
    )

    for _ in range(3):
        deployment_repository.create(db_session, app_a.id, None, "main")
    deployment_repository.create(db_session, app_b.id, None, "main")

    response_a = client.get("/dashboard", headers=_auth_header(tokens_a))
    response_b = client.get("/dashboard", headers=_auth_header(tokens_b))

    assert response_a.json()["data"]["deployments"] == 3
    assert response_b.json()["data"]["deployments"] == 1


def test_dashboard_counts_owned_applications(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_containers(monkeypatch)
    tokens_a = _register_and_login(client, _unique_user())
    tokens_b = _register_and_login(client, _unique_user())

    project_a = _create_project(client, tokens_a, "Apps Project A")
    project_b = _create_project(client, tokens_b, "Apps Project B")

    for i in range(2):
        application_repository.create(
            db_session, ApplicationCreate(project_id=project_a, name=f"api-a-{i}")
        )
    application_repository.create(
        db_session, ApplicationCreate(project_id=project_b, name="api-b")
    )

    response_a = client.get("/dashboard", headers=_auth_header(tokens_a))
    response_b = client.get("/dashboard", headers=_auth_header(tokens_b))

    assert response_a.json()["data"]["applications"] == 2
    assert response_b.json()["data"]["applications"] == 1


def test_dashboard_counts_active_alerts_by_severity(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_containers(monkeypatch)
    now = datetime.now(tz=UTC)

    for index, severity in enumerate(("critical", "critical", "warning")):
        alert_repository.create(
            db_session,
            fingerprint=f"dash-{index}",
            alert_name="HighHostCPUUsage",
            status=AlertStatus.firing,
            severity=severity,
            summary=None,
            description=None,
            labels={},
            annotations={},
            starts_at=now,
            ends_at=None,
        )
    alert_repository.create(
        db_session,
        fingerprint="dash-resolved",
        alert_name="HighHostCPUUsage",
        status=AlertStatus.resolved,
        severity="critical",
        summary=None,
        description=None,
        labels={},
        annotations={},
        starts_at=now,
        ends_at=now,
    )

    tokens = _register_and_login(client, _unique_user())
    body = client.get("/dashboard", headers=_auth_header(tokens)).json()["data"]

    assert body["alerts_active"] == 3
    assert body["alerts_critical"] == 2
    assert body["alerts_warning"] == 1
    assert body["alerts_info"] == 0


def test_dashboard_counts_containers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_containers(monkeypatch, running=7, stopped=3)
    tokens = _register_and_login(client, _unique_user())

    body = client.get("/dashboard", headers=_auth_header(tokens)).json()["data"]

    assert body["containers"] == 7
    assert body["containers_total"] == 10


def test_dashboard_containers_zero_when_docker_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail(**_kwargs: object) -> list[container_service.ContainerInfo]:
        raise RuntimeError("docker daemon tidak tersedia")

    monkeypatch.setattr(container_service, "list_containers", _fail)
    tokens = _register_and_login(client, _unique_user())

    body = client.get("/dashboard", headers=_auth_header(tokens)).json()["data"]

    assert body["containers"] == 0
    assert body["containers_total"] == 0
