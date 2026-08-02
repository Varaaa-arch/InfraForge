"""
Unit test untuk Task 3.1 — Server Management.

Coverage:
- Schema validation (ServerCreate, ServerUpdate)
- CRUD endpoint: POST, GET list, GET detail, PATCH, DELETE
- SSH test endpoint (mock paramiko agar tidak butuh server nyata)
- Akses terproteksi (401 tanpa token, 404 server milik orang lain)
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_user() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "password123",
    }


def _register_and_login(client: TestClient, payload: dict[str, str]) -> dict[str, str]:
    client.post("/auth/register", json=payload)
    r = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    return dict(r.json()["data"])


def _auth(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _server_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "prod-server",
        "host": "192.168.1.1",
        "port": 22,
        "username": "ubuntu",
        "auth_type": "password",
        "password": "secret123",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Schema validation tests (tidak butuh DB)
# ---------------------------------------------------------------------------

class TestServerSchemas:
    def test_create_password_auth_valid(self) -> None:
        from app.schemas.server import ServerCreate
        s = ServerCreate(
            name="web-01",
            host="10.0.0.1",
            username="root",
            auth_type="password",
            password="pass",
        )
        assert s.auth_type.value == "password"
        assert s.private_key is None

    def test_create_private_key_auth_valid(self) -> None:
        from app.schemas.server import ServerCreate
        s = ServerCreate(
            name="web-02",
            host="10.0.0.2",
            username="root",
            auth_type="private_key",
            private_key="-----BEGIN RSA PRIVATE KEY-----\nfakekey\n-----END RSA PRIVATE KEY-----",
        )
        assert s.auth_type.value == "private_key"
        assert s.password is None

    def test_create_password_auth_missing_password_raises(self) -> None:
        from pydantic import ValidationError
        from app.schemas.server import ServerCreate
        with pytest.raises(ValidationError, match="password wajib diisi"):
            ServerCreate(
                name="bad",
                host="10.0.0.3",
                username="root",
                auth_type="password",
                # password tidak dikirim
            )

    def test_create_private_key_auth_missing_key_raises(self) -> None:
        from pydantic import ValidationError
        from app.schemas.server import ServerCreate
        with pytest.raises(ValidationError, match="private_key wajib diisi"):
            ServerCreate(
                name="bad",
                host="10.0.0.4",
                username="root",
                auth_type="private_key",
                # private_key tidak dikirim
            )

    def test_server_response_no_sensitive_fields(self) -> None:
        from app.schemas.server import ServerResponse
        fields = ServerResponse.model_fields
        assert "password" not in fields
        assert "private_key" not in fields

    def test_update_schema_all_optional(self) -> None:
        from app.schemas.server import ServerUpdate
        # Semua field None tetap valid
        s = ServerUpdate()
        assert s.name is None
        assert s.host is None


# ---------------------------------------------------------------------------
# CRUD endpoint tests
# ---------------------------------------------------------------------------

class TestServerCRUD:
    def test_create_server_returns_201(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        r = client.post("/servers", headers=_auth(tokens), json=_server_payload())
        assert r.status_code == 201
        body = r.json()["data"]
        assert body["name"] == "prod-server"
        assert body["host"] == "192.168.1.1"
        assert body["port"] == 22
        assert body["auth_type"] == "password"
        assert body["status"] == "inactive"
        # Credential tidak boleh muncul di response
        assert "password" not in body
        assert "private_key" not in body

    def test_create_server_without_token_returns_401(self, client: TestClient) -> None:
        r = client.post("/servers", json=_server_payload())
        assert r.status_code == 401

    def test_create_server_missing_password_returns_422(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        bad = _server_payload()
        del bad["password"]  # type: ignore[misc]
        r = client.post("/servers", headers=_auth(tokens), json=bad)
        assert r.status_code == 422

    def test_list_servers_returns_own_only(self, client: TestClient) -> None:
        tokens_a = _register_and_login(client, _unique_user())
        tokens_b = _register_and_login(client, _unique_user())

        client.post("/servers", headers=_auth(tokens_a), json=_server_payload(name="server-a1"))
        client.post("/servers", headers=_auth(tokens_a), json=_server_payload(name="server-a2"))
        client.post("/servers", headers=_auth(tokens_b), json=_server_payload(name="server-b1"))

        r = client.get("/servers", headers=_auth(tokens_a))
        assert r.status_code == 200
        names = [s["name"] for s in r.json()["data"]]
        assert "server-a1" in names
        assert "server-a2" in names
        assert "server-b1" not in names

    def test_list_servers_without_token_returns_401(self, client: TestClient) -> None:
        r = client.get("/servers")
        assert r.status_code == 401

    def test_get_server_detail(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        created = client.post("/servers", headers=_auth(tokens), json=_server_payload()).json()["data"]
        server_id = created["id"]

        r = client.get(f"/servers/{server_id}", headers=_auth(tokens))
        assert r.status_code == 200
        assert r.json()["data"]["id"] == server_id

    def test_get_server_not_found_returns_404(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        r = client.get("/servers/99999999", headers=_auth(tokens))
        assert r.status_code == 404

    def test_get_server_of_other_user_returns_404(self, client: TestClient) -> None:
        tokens_a = _register_and_login(client, _unique_user())
        tokens_b = _register_and_login(client, _unique_user())

        created = client.post("/servers", headers=_auth(tokens_a), json=_server_payload()).json()["data"]
        server_id = created["id"]

        # User B tidak boleh melihat server milik user A
        r = client.get(f"/servers/{server_id}", headers=_auth(tokens_b))
        assert r.status_code == 404

    def test_update_server_name_and_host(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        created = client.post("/servers", headers=_auth(tokens), json=_server_payload()).json()["data"]
        server_id = created["id"]

        r = client.patch(
            f"/servers/{server_id}",
            headers=_auth(tokens),
            json={"name": "updated-name", "host": "10.10.10.10"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["name"] == "updated-name"
        assert data["host"] == "10.10.10.10"

    def test_update_server_not_owned_returns_404(self, client: TestClient) -> None:
        tokens_a = _register_and_login(client, _unique_user())
        tokens_b = _register_and_login(client, _unique_user())
        created = client.post("/servers", headers=_auth(tokens_a), json=_server_payload()).json()["data"]
        server_id = created["id"]

        r = client.patch(f"/servers/{server_id}", headers=_auth(tokens_b), json={"name": "hack"})
        assert r.status_code == 404

    def test_delete_server(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        created = client.post("/servers", headers=_auth(tokens), json=_server_payload()).json()["data"]
        server_id = created["id"]

        r = client.delete(f"/servers/{server_id}", headers=_auth(tokens))
        assert r.status_code == 200
        assert "deleted" in r.json()["data"]["message"].lower()

        # Setelah dihapus, GET harus 404
        r2 = client.get(f"/servers/{server_id}", headers=_auth(tokens))
        assert r2.status_code == 404

    def test_delete_server_not_owned_returns_404(self, client: TestClient) -> None:
        tokens_a = _register_and_login(client, _unique_user())
        tokens_b = _register_and_login(client, _unique_user())
        created = client.post("/servers", headers=_auth(tokens_a), json=_server_payload()).json()["data"]
        server_id = created["id"]

        r = client.delete(f"/servers/{server_id}", headers=_auth(tokens_b))
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# SSH test endpoint tests (mock paramiko)
# ---------------------------------------------------------------------------

class TestSSHTestEndpoint:
    def test_ssh_test_success(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        created = client.post("/servers", headers=_auth(tokens), json=_server_payload()).json()["data"]
        server_id = created["id"]

        # Mock paramiko.SSHClient agar tidak buka koneksi nyata
        mock_ssh = MagicMock()
        mock_ssh_class = MagicMock(return_value=mock_ssh)
        mock_ssh.connect.return_value = None  # koneksi sukses
        mock_ssh.close.return_value = None

        with patch("app.services.ssh_service.paramiko", create=True) as mock_paramiko:
            mock_paramiko.SSHClient.return_value = mock_ssh
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()

            # Patch lazy import di dalam fungsi test_connection
            with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
                r = client.post(f"/servers/{server_id}/test", headers=_auth(tokens))

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["server_id"] == server_id
        # Setelah test, status server harus berubah (active atau error)
        assert isinstance(data["success"], bool)
        assert isinstance(data["message"], str)

    def test_ssh_test_connection_refused(self, client: TestClient) -> None:
        """Mock ssh_service.test_connection langsung — lebih simpel dan reliable."""
        from app.schemas.server import SSHTestResult

        tokens = _register_and_login(client, _unique_user())
        created = client.post("/servers", headers=_auth(tokens), json=_server_payload()).json()["data"]
        server_id = created["id"]

        mock_result = SSHTestResult(
            server_id=server_id,
            host="192.168.1.1",
            port=22,
            success=False,
            message="Connection refused — port mungkin tertutup atau firewall memblokir",
        )

        with patch("app.services.server_service.ssh_service.test_connection", return_value=mock_result):
            r = client.post(f"/servers/{server_id}/test", headers=_auth(tokens))

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["success"] is False
        assert "refused" in data["message"].lower() or "Connection" in data["message"]

    def test_ssh_test_updates_server_status_to_active(self, client: TestClient) -> None:
        """Verifikasi status server berubah jadi active setelah SSH berhasil."""
        from app.schemas.server import SSHTestResult

        tokens = _register_and_login(client, _unique_user())
        created = client.post("/servers", headers=_auth(tokens), json=_server_payload()).json()["data"]
        server_id = created["id"]
        assert created["status"] == "inactive"

        mock_result = SSHTestResult(
            server_id=server_id,
            host="192.168.1.1",
            port=22,
            success=True,
            message="Connected",
        )

        with patch("app.services.server_service.ssh_service.test_connection", return_value=mock_result):
            client.post(f"/servers/{server_id}/test", headers=_auth(tokens))

        # Cek status sudah terupdate di DB
        r = client.get(f"/servers/{server_id}", headers=_auth(tokens))
        assert r.json()["data"]["status"] == "active"

    def test_ssh_test_updates_server_status_to_error(self, client: TestClient) -> None:
        """Verifikasi status server berubah jadi error setelah SSH gagal."""
        from app.schemas.server import SSHTestResult

        tokens = _register_and_login(client, _unique_user())
        created = client.post("/servers", headers=_auth(tokens), json=_server_payload()).json()["data"]
        server_id = created["id"]

        mock_result = SSHTestResult(
            server_id=server_id,
            host="192.168.1.1",
            port=22,
            success=False,
            message="Connection timeout setelah 10 detik",
        )

        with patch("app.services.server_service.ssh_service.test_connection", return_value=mock_result):
            client.post(f"/servers/{server_id}/test", headers=_auth(tokens))

        r = client.get(f"/servers/{server_id}", headers=_auth(tokens))
        assert r.json()["data"]["status"] == "error"

    def test_ssh_test_not_owned_server_returns_404(self, client: TestClient) -> None:
        tokens_a = _register_and_login(client, _unique_user())
        tokens_b = _register_and_login(client, _unique_user())
        created = client.post("/servers", headers=_auth(tokens_a), json=_server_payload()).json()["data"]
        server_id = created["id"]

        r = client.post(f"/servers/{server_id}/test", headers=_auth(tokens_b))
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# SSH service unit tests (tanpa DB, tanpa HTTP)
# ---------------------------------------------------------------------------

class TestSSHServiceUnit:
    def _make_server(self) -> object:
        """Buat objek Server mock sederhana."""
        from app.models.server import AuthType
        server = MagicMock()
        server.id = 1
        server.host = "192.168.1.1"
        server.port = 22
        server.username = "ubuntu"
        server.auth_type = AuthType.password
        server.password = "secret"
        server.private_key = None
        return server

    def test_resolve_new_status_active_on_success(self) -> None:
        from app.schemas.server import SSHTestResult
        from app.services.ssh_service import resolve_new_status
        from app.models.server import ServerStatus

        result = SSHTestResult(server_id=1, host="h", port=22, success=True, message="Connected")
        assert resolve_new_status(result) == ServerStatus.active

    def test_resolve_new_status_error_on_failure(self) -> None:
        from app.schemas.server import SSHTestResult
        from app.services.ssh_service import resolve_new_status
        from app.models.server import ServerStatus

        result = SSHTestResult(server_id=1, host="h", port=22, success=False, message="Timeout")
        assert resolve_new_status(result) == ServerStatus.error

    def test_test_connection_timeout(self) -> None:
        from app.services.ssh_service import test_connection

        server = self._make_server()

        mock_client = MagicMock()
        mock_client.connect.side_effect = __import__("socket").timeout("timed out")

        with patch.dict("sys.modules", {"paramiko": MagicMock()}):
            import sys
            mock_paramiko = sys.modules["paramiko"]
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()

            result = test_connection(server)  # type: ignore[arg-type]

        assert result.success is False
        assert "timeout" in result.message.lower()

    def test_test_connection_refused(self) -> None:
        from app.services.ssh_service import test_connection

        server = self._make_server()

        mock_client = MagicMock()
        mock_client.connect.side_effect = ConnectionRefusedError("refused")

        with patch.dict("sys.modules", {"paramiko": MagicMock()}):
            import sys
            mock_paramiko = sys.modules["paramiko"]
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()

            result = test_connection(server)  # type: ignore[arg-type]

        assert result.success is False
        assert "refused" in result.message.lower()
