from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to InfraForge!"}

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_ready_return_service_unavailable_when_dependencies_are_down() -> None:
    response = client.get("/ready")
    assert response.status_code in (200, 503)
    assert "database" in response.json()
    assert "redis" in response.json()


    
