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


def test_dashboard_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/dashboard")
    assert response.status_code == 401


def test_dashboard_with_no_projects(client: TestClient) -> None:
    tokens = _register_and_login(client, _unique_user())

    response = client.get("/dashboard", headers=_auth_header(tokens))
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["projects"] == 0
    assert body["deployments"] == 0
    assert body["containers"] == 0
    assert body["servers"] == 0


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
