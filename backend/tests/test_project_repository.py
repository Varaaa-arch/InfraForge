import uuid

from fastapi.testclient import TestClient


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


def _create_project(client: TestClient, tokens: dict[str, str], name: str = "Repo Project") -> int:
    response = client.post("/projects", headers=_auth_header(tokens), json={"name": name})
    return int(response.json()["data"]["id"])


def test_project_starts_without_repository_metadata(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    project_id = _create_project(client, tokens)

    response = client.get(f"/projects/{project_id}", headers=_auth_header(tokens))
    body = response.json()["data"]
    assert body["repository_url"] is None
    assert body["default_branch"] is None
    assert body["provider"] is None
    assert body["repository_connected_at"] is None


def test_link_repository_success(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    project_id = _create_project(client, tokens)

    response = client.patch(
        f"/projects/{project_id}/repository",
        headers=_auth_header(tokens),
        json={
            "repository_url": "https://github.com/zarrgvrd/infraforge",
            "provider": "github",
        },
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["repository_url"] == "https://github.com/zarrgvrd/infraforge"
    assert body["provider"] == "github"
    assert body["default_branch"] == "main"
    assert body["repository_connected_at"] is not None


def test_link_repository_with_custom_branch(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    project_id = _create_project(client, tokens)

    response = client.patch(
        f"/projects/{project_id}/repository",
        headers=_auth_header(tokens),
        json={
            "repository_url": "https://gitlab.com/team/app",
            "default_branch": "develop",
            "provider": "gitlab",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["default_branch"] == "develop"


def test_link_repository_with_invalid_url_returns_422(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    project_id = _create_project(client, tokens)

    response = client.patch(
        f"/projects/{project_id}/repository",
        headers=_auth_header(tokens),
        json={"repository_url": "not-a-valid-url", "provider": "github"},
    )
    assert response.status_code == 422


def test_link_repository_with_invalid_provider_returns_422(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    project_id = _create_project(client, tokens)

    response = client.patch(
        f"/projects/{project_id}/repository",
        headers=_auth_header(tokens),
        json={"repository_url": "https://sourceforge.net/x", "provider": "sourceforge"},
    )
    assert response.status_code == 422


def test_link_repository_by_non_owner_returns_403(client: TestClient) -> None:
    owner_tokens = _register_and_login(client, _unique_user())
    stranger_tokens = _register_and_login(client, _unique_user())
    project_id = _create_project(client, owner_tokens)

    response = client.patch(
        f"/projects/{project_id}/repository",
        headers=_auth_header(stranger_tokens),
        json={"repository_url": "https://github.com/x/y", "provider": "github"},
    )
    assert response.status_code == 403


def test_link_repository_without_token_returns_401(client: TestClient) -> None:
    response = client.patch(
        "/projects/1/repository",
        json={"repository_url": "https://github.com/x/y", "provider": "github"},
    )
    assert response.status_code == 401


def test_link_repository_on_nonexistent_project_returns_404(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())

    response = client.patch(
        "/projects/999999999/repository",
        headers=_auth_header(tokens),
        json={"repository_url": "https://github.com/x/y", "provider": "github"},
    )
    assert response.status_code == 404


def test_link_repository_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    tokens = _register_and_login(client, _unique_user())
    project_id = _create_project(client, tokens, name="Audit Repo Project")

    log_sink.clear()
    client.patch(
        f"/projects/{project_id}/repository",
        headers=_auth_header(tokens),
        json={"repository_url": "https://github.com/x/y", "provider": "github"},
    )

    assert any(
        "[UPDATE_PROJECT_REPOSITORY]" in msg and "project=audit-repo-project" in msg
        for msg in log_sink
    )


def test_relink_repository_overwrites_previous_metadata(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    project_id = _create_project(client, tokens)

    client.patch(
        f"/projects/{project_id}/repository",
        headers=_auth_header(tokens),
        json={"repository_url": "https://github.com/old/repo", "provider": "github"},
    )
    response = client.patch(
        f"/projects/{project_id}/repository",
        headers=_auth_header(tokens),
        json={"repository_url": "https://gitlab.com/new/repo", "provider": "gitlab"},
    )

    body = response.json()["data"]
    assert body["repository_url"] == "https://gitlab.com/new/repo"
    assert body["provider"] == "gitlab"
