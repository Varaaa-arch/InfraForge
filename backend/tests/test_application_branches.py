import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.application import Application


def _register_and_login(client: TestClient) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "username": f"branch_{suffix}",
        "email": f"branch_{suffix}@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=payload)
    response = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    tokens = response.json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _create_project(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/projects",
        json={"name": f"Branch Project {uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return int(response.json()["data"]["id"])


def _create_application(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    **overrides: object,
) -> dict[str, object]:
    body: dict[str, object] = {
        "project_id": project_id,
        "name": f"app-{uuid.uuid4().hex[:6]}",
        "repository": "https://github.com/org/repo",
        "branch": "main",
    }
    body.update(overrides)
    response = client.post("/applications", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_create_application_defaults_webhook_branches_to_branch(
    client: TestClient,
) -> None:
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)

    app = _create_application(client, headers, project_id, branch="develop")

    assert app["webhook_branches"] == ["develop"]


def test_create_application_normalizes_webhook_branches(
    client: TestClient,
) -> None:
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)

    app = _create_application(
        client,
        headers,
        project_id,
        webhook_branches=[" develop ", "release"],
    )

    assert app["webhook_branches"] == ["develop", "release"]


@pytest.mark.parametrize(
    "branches",
    [
        [],
        ["main", "main"],
        ["bad branch"],
        ["x" * 101],
        [f"branch-{index}" for index in range(21)],
    ],
)
def test_create_application_rejects_invalid_webhook_branches(
    client: TestClient, branches: list[str]
) -> None:
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)

    response = client.post(
        "/applications",
        json={
            "project_id": project_id,
            "name": f"app-{uuid.uuid4().hex[:6]}",
            "repository": "https://github.com/org/repo",
            "branch": "main",
            "webhook_branches": branches,
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_update_application_rejects_duplicate_webhook_branches(
    client: TestClient,
) -> None:
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    app = _create_application(client, headers, project_id)

    response = client.patch(
        f"/applications/{app['id']}",
        json={"webhook_branches": ["main", "main"]},
        headers=headers,
    )

    assert response.status_code == 422


def test_response_falls_back_to_branch_for_legacy_null_filter(
    client: TestClient, db_session: Session
) -> None:
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    app = _create_application(client, headers, project_id, branch="develop")

    model = db_session.get(Application, int(app["id"]))
    assert model is not None
    model.webhook_branches = None
    db_session.commit()

    response = client.get(f"/applications/{app['id']}", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["webhook_branches"] == ["develop"]
