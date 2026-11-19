"""Test riwayat versi deployment: tag, identitas pemicu, dan rollback."""

from __future__ import annotations

import uuid
from contextlib import nullcontext
from unittest.mock import patch

from app.models.deployment import DeploymentStatus
from app.repositories import deployment_repository


def _register_and_login(client) -> tuple[dict[str, str], str]:
    suffix = uuid.uuid4().hex[:8]
    username = f"ver_{suffix}"
    user = {
        "username": username,
        "email": f"{username}@t.com",
        "password": "pass1234",
    }
    client.post("/auth/register", json=user)
    response = client.post(
        "/auth/login",
        data={"username": username, "password": user["password"]},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}, username


def _create_project(client, headers) -> int:
    response = client.post(
        "/projects",
        json={"name": f"ver-{uuid.uuid4().hex[:6]}", "description": "test"},
        headers=headers,
    )
    return int(response.json()["data"]["id"])


def _create_server(client, headers) -> int:
    response = client.post(
        "/servers",
        json={
            "name": "ver-server",
            "host": "192.0.2.55",
            "port": 22,
            "username": "ubuntu",
            "auth_type": "password",
            "password": "secret",
        },
        headers=headers,
    )
    return int(response.json()["data"]["id"])


def _create_app(client, headers, project_id: int) -> int:
    response = client.post(
        "/applications",
        json={
            "project_id": project_id,
            "name": f"app-{uuid.uuid4().hex[:6]}",
            "repository": "https://github.com/org/repo",
            "branch": "main",
        },
        headers=headers,
    )
    return int(response.json()["data"]["id"])


def test_manual_trigger_records_tag_and_triggered_by(client, db_session) -> None:
    headers, username = _register_and_login(client)
    project_id = _create_project(client, headers)
    server_id = _create_server(client, headers)
    app_id = _create_app(client, headers, project_id)

    with (
        patch("app.services.deployment_service._run_deployment"),
        patch("app.services.deployment_queue.redis_client") as redis_mock,
    ):
        redis_mock.exists.return_value = 0
        redis_mock.get.return_value = None
        redis_mock.set.return_value = True
        response = client.post(
            "/deployments",
            json={
                "application_id": app_id,
                "server_id": server_id,
                "tag": "v1.2.3",
            },
            headers=headers,
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["tag"] == "v1.2.3"
    assert data["triggered_by"] == username

    deployment = deployment_repository.get_by_id(db_session, int(data["id"]))
    assert deployment is not None
    assert deployment.tag == "v1.2.3"
    assert deployment.triggered_by == username


def test_ci_trigger_records_tag_and_token_identity(client, db_session) -> None:
    headers, _username = _register_and_login(client)
    project_id = _create_project(client, headers)
    _create_server(client, headers)
    app_id = _create_app(client, headers, project_id)

    token_response = client.post(
        f"/projects/{project_id}/deploy-tokens",
        json={"name": "pipeline-versi", "application_id": app_id},
        headers=headers,
    )
    assert token_response.status_code == 201
    token = token_response.json()["data"]["token"]

    with (
        patch("app.services.deployment_queue.redis_client") as redis_mock,
        patch("app.services.deployment_queue.run_deployment_background"),
    ):
        redis_mock.exists.return_value = 0
        redis_mock.get.return_value = None
        redis_mock.set.return_value = True
        response = client.post(
            f"/v1/deploy/webhook/{token}",
            json={"tag": "v2.0.0"},
            headers={"Idempotency-Key": f"ver-{uuid.uuid4().hex}"},
        )

    assert response.status_code == 202, response.text
    deployment_id = response.json()["data"]["deployment_ids"][0]
    deployment = deployment_repository.get_by_id(db_session, deployment_id)
    assert deployment is not None
    assert deployment.tag == "v2.0.0"
    assert deployment.triggered_by == "deploy-token:pipeline-versi"
    assert deployment.trigger_source == "ci_token"


def test_deployment_response_exposes_version_metadata(client, db_session) -> None:
    headers, username = _register_and_login(client)
    project_id = _create_project(client, headers)
    server_id = _create_server(client, headers)
    app_id = _create_app(client, headers, project_id)

    deployment = deployment_repository.create(
        db_session,
        app_id,
        server_id,
        "main",
        tag="v3.1.0",
        triggered_by=username,
    )
    deployment_repository.update_status(
        db_session, deployment, DeploymentStatus.success, tag="v3.1.0"
    )

    response = client.get(f"/deployments/{deployment.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tag"] == "v3.1.0"
    assert data["triggered_by"] == username


def test_rollback_background_runs_with_snapshotted_version(client, db_session) -> None:
    from app.models.application import AppStatus
    from app.repositories import application_repository
    from app.services import deployment_queue, deployment_service

    headers, username = _register_and_login(client)
    project_id = _create_project(client, headers)
    server_id = _create_server(client, headers)
    app_id = _create_app(client, headers, project_id)

    target = deployment_repository.create(
        db_session,
        app_id,
        server_id,
        "main",
        tag="v4.2.0",
        commit_sha="f" * 40,
        triggered_by="ci",
    )
    deployment_repository.update_status(
        db_session,
        target,
        DeploymentStatus.success,
        compose_path_snapshot="deploy/legacy-compose.yml",
    )
    rollback = deployment_service.create_rollback_deployment(
        db_session,
        target.id,
        app_id,
        triggered_by=username,
    )

    with (
        patch("app.services.deployment_queue.redis_client") as redis_mock,
        patch(
            "app.services.deployment_queue.SessionLocal",
            return_value=nullcontext(db_session),
        ),
        patch(
            "app.services.deployment_service._run_deployment"
        ) as run_mock,
    ):
        redis_mock.set.return_value = True
        redis_mock.delete.return_value = 1

        deployment_queue.run_deployment_background(
            deployment_id=rollback.id,
            application_id=app_id,
            server_id=server_id,
        )

    executed = run_mock.call_args.args[1]
    assert executed.id == rollback.id
    assert executed.tag == "v4.2.0"
    assert executed.commit_sha == "f" * 40
    assert executed.compose_path_snapshot == "deploy/legacy-compose.yml"
    assert executed.rollback_of == target.id

    db_session.expire_all()
    app = application_repository.get_by_id(db_session, app_id)
    assert app is not None
    assert app.status == AppStatus.running
