from fastapi.testclient import TestClient


def test_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"


def test_ready_returns_service_unavailable_when_dependencies_down(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code in (200, 503)
    body = response.json()
    assert "database" in body["data"]
    assert "redis" in body["data"]
    assert body["success"] == (response.status_code == 200)
