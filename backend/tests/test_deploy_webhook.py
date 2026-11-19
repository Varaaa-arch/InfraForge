"""Test webhook receiver deployment: GitHub/GitLab native + CI sederhana.

Semua interaksi Redis dan background deployment di-mock. Signature dihitung
dengan HMAC-SHA256 nyata agar jalur verifikasi ikut teruji.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.middleware.audit_middleware import match_audit_rule
from app.repositories import deployment_repository
from app.services import deployment_queue

from tests.test_deploy_tokens import (
    _create_application,
    _create_token,
    _setup_deployable,
)


def _signature(raw_body: bytes, token: str) -> str:
    digest = hmac.new(
        key=token.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def _github_payload(
    *,
    repo_url: str = "https://github.com/org/repo",
    branch: str = "main",
    commit_sha: str = "abc123def456",
) -> dict[str, object]:
    return {
        "ref": f"refs/heads/{branch}",
        "repository": {
            "full_name": "org/repo",
            "html_url": repo_url,
            "clone_url": f"{repo_url}.git",
        },
        "head_commit": {"id": commit_sha, "message": "test"},
    }


def _gitlab_payload(
    *,
    repo_url: str = "https://gitlab.com/org/repo",
    branch: str = "main",
    commit_sha: str = "deadbeef1234",
) -> dict[str, object]:
    return {
        "object_kind": "push",
        "ref": f"refs/heads/{branch}",
        "checkout_sha": commit_sha,
        "repository": {"git_http_url": repo_url, "homepage": repo_url},
        "commits": [{"id": commit_sha}],
    }


def _post_github(
    client: TestClient,
    token: str,
    payload: dict[str, object],
    *,
    delivery: str = "delivery-1",
    event: str = "push",
) -> object:
    raw = json.dumps(payload).encode("utf-8")
    return client.post(
        f"/v1/deploy/webhook/{token}",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": event,
            "X-Hub-Signature-256": _signature(raw, token),
            "X-GitHub-Delivery": delivery,
        },
    )


def _post_gitlab(
    client: TestClient,
    token: str,
    payload: dict[str, object],
    *,
    secret: str | None = None,
    event_id: str = "gl-event-1",
) -> object:
    return client.post(
        f"/v1/deploy/webhook/{token}",
        json=payload,
        headers={
            "X-Gitlab-Event": "Push Hook",
            "X-Gitlab-Token": secret if secret is not None else token,
            "X-Gitlab-Event-UUID": event_id,
        },
    )


def _set_webhook_branches(
    client: TestClient,
    headers: dict[str, str],
    application_id: object,
    branches: list[str],
) -> dict[str, object]:
    response = client.patch(
        f"/applications/{application_id}",
        json={"webhook_branches": branches},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.fixture()
def queue_mocks() -> Generator[tuple[object, object], None, None]:
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


# ---------------------------------------------------------------------------
# CI sederhana
# ---------------------------------------------------------------------------

def test_ci_simple_schedules_deployment(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _redis, background_mock = queue_mocks
    _user, headers, project_id, server_id, app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    response = client.post(f"/v1/deploy/webhook/{data['token']}", json={})
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["accepted"] is True
    assert body["source"] == "ci"
    assert body["deployment_ids"] == [body["deployments"][0]["deployment_id"]]
    assert body["deployments"][0]["application_id"] == app["id"]

    deployment = deployment_repository.get_by_id(
        db_session, body["deployment_ids"][0]
    )
    assert deployment is not None
    assert deployment.trigger_source == "ci_token"
    assert deployment.server_id == server_id
    background_mock.assert_called_once_with(
        deployment_id=deployment.id,
        application_id=app["id"],
        server_id=server_id,
    )


def test_ci_simple_multi_app_requires_application_id(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    _create_application(client, headers, project_id, name="worker")
    data = _create_token(client, headers, project_id)

    response = client.post(f"/v1/deploy/webhook/{data['token']}", json={})
    assert response.status_code == 422
    assert "application_id" in response.json()["message"]


def test_ci_simple_conflict_when_running(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    redis_mock, background_mock = queue_mocks
    redis_mock.get.return_value = "42"
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    response = client.post(f"/v1/deploy/webhook/{data['token']}", json={})
    assert response.status_code == 409
    assert "42" in response.json()["message"]
    background_mock.assert_not_called()


def test_ci_simple_app_scoped_token(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, first = _setup_deployable(
        client, db_session
    )
    _create_application(client, headers, project_id, name="worker")
    data = _create_token(
        client, headers, project_id, application_id=first["id"]
    )

    response = client.post(f"/v1/deploy/webhook/{data['token']}", json={})
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["deployments"][0]["application_id"] == first["id"]


# ---------------------------------------------------------------------------
# GitHub native
# ---------------------------------------------------------------------------

def test_github_push_schedules_deployment(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    response = _post_github(client, str(data["token"]), _github_payload())
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["accepted"] is True
    assert body["source"] == "github"
    assert body["event"] == "push"
    assert body["branch"] == "main"
    assert len(body["deployment_ids"]) == 1

    deployment = deployment_repository.get_by_id(
        db_session, body["deployment_ids"][0]
    )
    assert deployment is not None
    assert deployment.application_id == app["id"]
    assert deployment.branch == "main"
    assert deployment.trigger_source == "ci_token"


def test_github_invalid_signature_is_rejected(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)
    raw = json.dumps(_github_payload()).encode("utf-8")

    response = client.post(
        f"/v1/deploy/webhook/{data['token']}",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=deadbeef",
            "X-GitHub-Delivery": "bad-signature",
        },
    )
    assert response.status_code == 401
    assert "Signature" in response.json()["message"]


def test_github_non_push_event_is_ignored(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    response = _post_github(
        client, str(data["token"]), {"zenith": "hook"}, event="ping"
    )
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["accepted"] is False
    assert body["deployment_ids"] == []
    assert "ping" in body["message"]


def test_github_no_matching_application(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    response = _post_github(
        client,
        str(data["token"]),
        _github_payload(repo_url="https://github.com/org/other"),
    )
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["accepted"] is False
    assert body["deployment_ids"] == []


def test_github_duplicate_delivery_is_idempotent(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    with patch.object(
        deployment_queue, "is_duplicate_delivery", side_effect=[None, 99]
    ):
        first = _post_github(
            client, str(data["token"]), _github_payload(), delivery="same"
        )
        second = _post_github(
            client, str(data["token"]), _github_payload(), delivery="same"
        )

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    body = second.json()["data"]
    assert body["accepted"] is False
    assert body["deployment_ids"] == [99]
    assert "sudah pernah diproses" in body["message"]
    assert len(
        deployment_repository.list_by_application(db_session, int(app["id"]))
    ) == 1


def test_github_app_scoped_token_requires_matching_repo(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    data = _create_token(
        client, headers, project_id, application_id=_app["id"]
    )

    response = _post_github(
        client,
        str(data["token"]),
        _github_payload(repo_url="https://github.com/org/other"),
    )
    assert response.status_code == 202, response.text
    assert response.json()["data"]["accepted"] is False


def test_github_project_token_deploys_all_matching_apps(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    _create_application(client, headers, project_id, name="worker")
    data = _create_token(client, headers, project_id)

    response = _post_github(client, str(data["token"]), _github_payload())
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["accepted"] is True
    assert len(body["deployment_ids"]) == 2


def test_github_push_uses_configured_webhook_branches(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, app = _setup_deployable(
        client, db_session
    )
    _set_webhook_branches(client, headers, app["id"], ["develop"])
    data = _create_token(client, headers, project_id)

    response = _post_github(
        client, str(data["token"]), _github_payload(branch="develop")
    )
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["accepted"] is True
    assert body["branch"] == "develop"

    deployment = deployment_repository.get_by_id(
        db_session, body["deployment_ids"][0]
    )
    assert deployment is not None
    assert deployment.application_id == app["id"]
    assert deployment.branch == "develop"


def test_github_push_rejects_branch_outside_filter(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, app = _setup_deployable(
        client, db_session
    )
    _set_webhook_branches(client, headers, app["id"], ["develop"])
    data = _create_token(client, headers, project_id)

    response = _post_github(client, str(data["token"]), _github_payload())
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["accepted"] is False
    assert body["deployment_ids"] == []


def test_project_token_filters_apps_by_webhook_branch(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, app = _setup_deployable(
        client, db_session
    )
    _set_webhook_branches(client, headers, app["id"], ["develop"])
    _create_application(client, headers, project_id, name="worker")
    data = _create_token(client, headers, project_id)

    response = _post_github(
        client, str(data["token"]), _github_payload(branch="develop")
    )
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["accepted"] is True
    assert len(body["deployment_ids"]) == 1

    deployment = deployment_repository.get_by_id(
        db_session, body["deployment_ids"][0]
    )
    assert deployment is not None
    assert deployment.application_id == app["id"]


# ---------------------------------------------------------------------------
# GitLab native
# ---------------------------------------------------------------------------

def test_gitlab_push_schedules_deployment(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)
    payload = _gitlab_payload(repo_url="https://github.com/org/repo")

    response = _post_gitlab(client, str(data["token"]), payload)
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["accepted"] is True, body
    assert body["source"] == "gitlab"
    assert body["branch"] == "main"

    deployment = deployment_repository.get_by_id(
        db_session, body["deployment_ids"][0]
    )
    assert deployment is not None
    assert deployment.application_id == app["id"]


def test_gitlab_push_uses_configured_webhook_branches(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, app = _setup_deployable(
        client, db_session
    )
    _set_webhook_branches(client, headers, app["id"], ["release"])
    data = _create_token(client, headers, project_id)
    payload = _gitlab_payload(
        repo_url="https://github.com/org/repo", branch="release"
    )

    response = _post_gitlab(client, str(data["token"]), payload)
    assert response.status_code == 202, response.text
    body = response.json()["data"]
    assert body["accepted"] is True, body
    assert body["branch"] == "release"

    deployment = deployment_repository.get_by_id(
        db_session, body["deployment_ids"][0]
    )
    assert deployment is not None
    assert deployment.application_id == app["id"]
    assert deployment.branch == "release"


def test_gitlab_invalid_secret_is_rejected(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    response = _post_gitlab(
        client,
        str(data["token"]),
        _gitlab_payload(repo_url="https://github.com/org/repo"),
        secret="wrong",
    )
    assert response.status_code == 401
    assert "Secret" in response.json()["message"]


# ---------------------------------------------------------------------------
# Payload invalid & audit
# ---------------------------------------------------------------------------

def test_webhook_invalid_json_is_rejected(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, _app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id)

    response = client.post(
        f"/v1/deploy/webhook/{data['token']}",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert "JSON" in response.json()["message"]


def test_webhook_audit_rule_redacts_token() -> None:
    matched = match_audit_rule(
        "POST", "/v1/deploy/webhook/dt_abc_secret"
    )
    assert matched is not None
    assert matched[0].action == "DEPLOY_WEBHOOK"
    assert matched[1] == {}


def test_webhook_audit_event_uses_token_name_and_redacted_path(
    client: TestClient, db_session: Session, queue_mocks: tuple[object, object]
) -> None:
    _user, headers, project_id, _server_id, app = _setup_deployable(
        client, db_session
    )
    data = _create_token(client, headers, project_id, name="gh-actions")

    with patch("app.services.audit_service.record") as record_mock:
        response = _post_github(client, str(data["token"]), _github_payload())
    assert response.status_code == 202

    recorded = [call.args[0] for call in record_mock.call_args_list]
    events = [event for event in recorded if event.action == "DEPLOY_WEBHOOK"]
    assert len(events) == 1
    event = events[0]
    assert event.username == "deploy-token:gh-actions"
    assert event.resource_id == str(data["id"])
    assert event.path == "/v1/deploy/webhook/[redacted]"
    assert event.details["source"] == "github"
    assert event.details["outcome"] == "scheduled"
    assert event.details["application_ids"] == str(app["id"])
    assert str(data["token"]) not in str(event.details)
    assert str(data["token"]) not in event.path


def test_webhook_invalid_token_audit_is_redacted(
    client: TestClient, db_session: Session
) -> None:
    token = "dt_deadbeef_" + "0" * 64

    with patch("app.services.audit_service.record") as record_mock:
        response = client.post(f"/v1/deploy/webhook/{token}", json={})
    assert response.status_code == 404

    recorded = [call.args[0] for call in record_mock.call_args_list]
    events = [event for event in recorded if event.action == "DEPLOY_WEBHOOK"]
    assert len(events) == 1
    assert events[0].path == "/v1/deploy/webhook/[redacted]"
    assert events[0].details["outcome"] == "invalid_token"
    assert token not in events[0].path
    assert token not in str(events[0].details)
