import uuid
from fastapi.testclient import TestClient

def _unique_user() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "password123",
    }

def test_every_request_gets_logged(client: TestClient, log_sink: list[str]) -> None:
    client.get("/health")

    assert any("GET /health" in message and "status=200" in message for message in log_sink)

def test_failed_request_logged_with_status_code(client: TestClient, log_sink: list[str]) -> None:
    client.get("/does-not-exist")

    assert any("status=404" in message for message in log_sink)

def test_register_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    payload = _unique_user()
    client.post("/auth/register", json=payload)

    assert any(f"[REGISTER] user={payload['username']}" in message for message in log_sink)

def test_login_success_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    payload = _unique_user()
    client.post("/auth/register", json=payload)

    log_sink.clear()
    client.post(
        "/auth/login", 
        data={"username": payload["username"], "password": payload["password"]},
    )

    assert any(f"[LOGIN] user={payload['username']}" in message for message in log_sink)

def test_login_failure_triggers_audit_log(client: TestClient, log_sink: list[str]) -> None:
    payload = _unique_user()
    client.post("/auth/register", json=payload)

    log_sink.clear()
    client.post(
        "/auth/login", 
        data={"username": payload["username"], "password": "wrong-password"},
    )

    assert any(f"[LOGIN_FAILED] user={payload['username']}" in message for message in log_sink)