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


def test_create_project(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())

    response = client.post(
        "/projects", headers=_auth_header(tokens), json={"name": "My Test Project"}
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["name"] == "My Test Project"
    assert body["slug"] == "my-test-project"
    assert body["visibility"] == "private"


def test_create_project_without_token_returns_401(client: TestClient) -> None:
    response = client.post("/projects", json={"name": "No Auth Project"})
    assert response.status_code == 401


def test_duplicate_project_name_gets_unique_slug(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())

    first = client.post("/projects", headers=_auth_header(tokens), json={"name": "Same Name"})
    second = client.post("/projects", headers=_auth_header(tokens), json={"name": "Same Name"})

    assert first.json()["data"]["slug"] == "same-name"
    assert second.json()["data"]["slug"] == "same-name-2"


def test_list_projects_returns_only_own_projects(client: TestClient) -> None:
    tokens_a = _register_and_login(client, _unique_user())
    tokens_b = _register_and_login(client, _unique_user())

    client.post("/projects", headers=_auth_header(tokens_a), json={"name": "Project A"})
    client.post("/projects", headers=_auth_header(tokens_b), json={"name": "Project B"})

    response = client.get("/projects", headers=_auth_header(tokens_a))
    names = [p["name"] for p in response.json()["data"]]
    assert names == ["Project A"]


def test_get_private_project_by_non_owner_returns_404(client: TestClient) -> None:
    owner_tokens = _register_and_login(client, _unique_user())
    stranger_tokens = _register_and_login(client, _unique_user())

    create_response = client.post(
        "/projects", headers=_auth_header(owner_tokens), json={"name": "Secret Project"}
    )
    project_id = create_response.json()["data"]["id"]

    response = client.get(f"/projects/{project_id}", headers=_auth_header(stranger_tokens))
    assert response.status_code == 404


def test_get_public_project_by_non_owner_returns_200(client: TestClient) -> None:
    owner_tokens = _register_and_login(client, _unique_user())
    stranger_tokens = _register_and_login(client, _unique_user())

    create_response = client.post(
        "/projects",
        headers=_auth_header(owner_tokens),
        json={"name": "Open Project", "visibility": "public"},
    )
    project_id = create_response.json()["data"]["id"]

    response = client.get(f"/projects/{project_id}", headers=_auth_header(stranger_tokens))
    assert response.status_code == 200


def test_get_nonexistent_project_returns_404(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    response = client.get("/projects/999999999", headers=_auth_header(tokens))
    assert response.status_code == 404


def test_update_project_by_owner(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    create_response = client.post(
        "/projects", headers=_auth_header(tokens), json={"name": "Original Name"}
    )
    project_id = create_response.json()["data"]["id"]

    response = client.patch(
        f"/projects/{project_id}",
        headers=_auth_header(tokens),
        json={"description": "Updated description", "visibility": "public"},
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["description"] == "Updated description"
    assert body["visibility"] == "public"
    assert body["slug"] == "original-name"


def test_update_project_by_non_owner_returns_403(client: TestClient) -> None:
    owner_tokens = _register_and_login(client, _unique_user())
    stranger_tokens = _register_and_login(client, _unique_user())

    create_response = client.post(
        "/projects", headers=_auth_header(owner_tokens), json={"name": "Owned Project"}
    )
    project_id = create_response.json()["data"]["id"]

    response = client.patch(
        f"/projects/{project_id}",
        headers=_auth_header(stranger_tokens),
        json={"name": "Hijacked"},
    )
    assert response.status_code == 403


def test_update_project_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    tokens = _register_and_login(client, _unique_user())
    create_response = client.post(
        "/projects", headers=_auth_header(tokens), json={"name": "Audit Project"}
    )
    project_id = create_response.json()["data"]["id"]

    log_sink.clear()
    client.patch(
        f"/projects/{project_id}", headers=_auth_header(tokens), json={"description": "x"}
    )

    assert any("[UPDATE_PROJECT]" in msg and "project=audit-project" in msg for msg in log_sink)


def test_delete_project_by_owner(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())
    create_response = client.post(
        "/projects", headers=_auth_header(tokens), json={"name": "To Delete"}
    )
    project_id = create_response.json()["data"]["id"]

    delete_response = client.delete(f"/projects/{project_id}", headers=_auth_header(tokens))
    assert delete_response.status_code == 200

    get_response = client.get(f"/projects/{project_id}", headers=_auth_header(tokens))
    assert get_response.status_code == 404


def test_delete_project_by_non_owner_returns_403(client: TestClient) -> None:
    owner_tokens = _register_and_login(client, _unique_user())
    stranger_tokens = _register_and_login(client, _unique_user())

    create_response = client.post(
        "/projects", headers=_auth_header(owner_tokens), json={"name": "Protected Project"}
    )
    project_id = create_response.json()["data"]["id"]

    response = client.delete(f"/projects/{project_id}", headers=_auth_header(stranger_tokens))
    assert response.status_code == 403


def test_create_project_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    tokens = _register_and_login(client, _unique_user())

    log_sink.clear()
    client.post("/projects", headers=_auth_header(tokens), json={"name": "Logged Project"})

    assert any("[CREATE_PROJECT]" in msg and "project=logged-project" in msg for msg in log_sink)


def test_delete_project_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    tokens = _register_and_login(client, _unique_user())
    create_response = client.post(
        "/projects", headers=_auth_header(tokens), json={"name": "Delete Log Project"}
    )
    project_id = create_response.json()["data"]["id"]

    log_sink.clear()
    client.delete(f"/projects/{project_id}", headers=_auth_header(tokens))

    assert any(
        "[DELETE_PROJECT]" in msg and "project=delete-log-project" in msg for msg in log_sink
    )
