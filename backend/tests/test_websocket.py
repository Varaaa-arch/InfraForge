"""
Unit & Integration test untuk Task 3.9 — Live Logs via WebSocket.

Coverage:
- _make_log_file / _append_log (deployment_service helpers)
- _run_compose dengan log_file parameter
- _run_deployment log integration
- _wait_for_log_path / _stream_log_file (websocket helpers)
- WebSocket endpoint: auth, ownership, stream, sentinel, error paths
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.deployment import DeploymentStatus


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_mock_deployment(
    dep_id: int = 1,
    app_id: int = 1,
    status: DeploymentStatus = DeploymentStatus.deploying,
    log_path: str | None = None,
) -> MagicMock:
    dep = MagicMock()
    dep.id = dep_id
    dep.application_id = app_id
    dep.status = status
    dep.log_path = log_path
    dep.branch = "main"
    dep.server_id = 1
    return dep


def _make_mock_app(app_id: int = 1, project_id: int = 1) -> MagicMock:
    app = MagicMock()
    app.id = app_id
    app.project_id = project_id
    app.repository = "https://github.com/org/repo.git"
    app.branch = "main"
    app.compose_path = "docker-compose.yml"
    return app


def _make_mock_project(project_id: int = 1, owner_id: int = 1) -> MagicMock:
    proj = MagicMock()
    proj.id = project_id
    proj.owner_id = owner_id
    return proj


def _make_mock_user(user_id: int = 1) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.is_active = True
    user.username = f"user_{user_id}"
    return user


# ---------------------------------------------------------------------------
# Unit: _make_log_file, _append_log
# ---------------------------------------------------------------------------

class TestMakeLogFile:
    def test_creates_file_in_tmp(self) -> None:
        from app.services.deployment_service import _make_log_file  # type: ignore[attr-defined]

        log_file = _make_log_file(deployment_id=9999)
        try:
            assert log_file.exists()
            assert log_file.name == "deployment_9999.log"
            assert log_file.parent == Path(tempfile.gettempdir())
        finally:
            log_file.unlink(missing_ok=True)

    def test_returns_path_object(self) -> None:
        from app.services.deployment_service import _make_log_file  # type: ignore[attr-defined]

        log_file = _make_log_file(deployment_id=1234)
        try:
            assert isinstance(log_file, Path)
        finally:
            log_file.unlink(missing_ok=True)

    def test_idempotent_for_same_id(self) -> None:
        from app.services.deployment_service import _make_log_file  # type: ignore[attr-defined]

        f1 = _make_log_file(deployment_id=5678)
        f2 = _make_log_file(deployment_id=5678)
        try:
            assert f1 == f2
            assert f1.exists()
        finally:
            f1.unlink(missing_ok=True)


class TestAppendLog:
    def test_appends_text_to_file(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _append_log  # type: ignore[attr-defined]

        log_file = tmp_path / "test.log"
        log_file.touch()
        _append_log(log_file, "line1\n")
        _append_log(log_file, "line2\n")
        content = log_file.read_text()
        assert "line1\n" in content
        assert "line2\n" in content

    def test_does_not_overwrite(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _append_log  # type: ignore[attr-defined]

        log_file = tmp_path / "test.log"
        log_file.write_text("existing\n")
        _append_log(log_file, "new line\n")
        content = log_file.read_text()
        assert content.startswith("existing\n")
        assert "new line\n" in content

    def test_empty_string_writes_nothing_new(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _append_log  # type: ignore[attr-defined]

        log_file = tmp_path / "test.log"
        log_file.touch()
        _append_log(log_file, "")
        assert log_file.read_text() == ""


# ---------------------------------------------------------------------------
# Unit: _run_compose with log_file
# ---------------------------------------------------------------------------

class TestRunComposeWithLogFile:
    def test_writes_header_to_log(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _run_compose  # type: ignore[attr-defined]

        log_file = tmp_path / "deploy.log"
        log_file.touch()
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = "build output\n"
        ok.stderr = ""
        with patch("subprocess.run", return_value=ok):
            _run_compose(tmp_path, "docker-compose.yml", log_file=log_file)
        content = log_file.read_text()
        assert "[InfraForge] Running:" in content

    def test_writes_stdout_to_log(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _run_compose  # type: ignore[attr-defined]

        log_file = tmp_path / "deploy.log"
        log_file.touch()
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = "Step 1/3: FROM python\n"
        ok.stderr = ""
        with patch("subprocess.run", return_value=ok):
            _run_compose(tmp_path, "docker-compose.yml", log_file=log_file)
        assert "Step 1/3: FROM python" in log_file.read_text()

    def test_writes_error_to_log_on_failure(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _run_compose  # type: ignore[attr-defined]

        log_file = tmp_path / "deploy.log"
        log_file.touch()
        fail = MagicMock()
        fail.returncode = 1
        fail.stdout = ""
        fail.stderr = "Build failed: missing layer\n"
        with patch("subprocess.run", return_value=fail):
            with pytest.raises(RuntimeError):
                _run_compose(tmp_path, "docker-compose.yml", log_file=log_file)
        content = log_file.read_text()
        assert "[InfraForge] ERROR:" in content

    def test_no_log_file_still_works(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _run_compose  # type: ignore[attr-defined]

        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = "ok"
        ok.stderr = ""
        with patch("subprocess.run", return_value=ok):
            stdout, _ = _run_compose(tmp_path, "docker-compose.yml", log_file=None)
        assert "ok" in stdout

    def test_stderr_written_to_log_on_success(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _run_compose  # type: ignore[attr-defined]

        log_file = tmp_path / "deploy.log"
        log_file.touch()
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = ""
        ok.stderr = "WARNING: deprecated flag\n"
        with patch("subprocess.run", return_value=ok):
            _run_compose(tmp_path, "docker-compose.yml", log_file=log_file)
        assert "WARNING: deprecated flag" in log_file.read_text()


# ---------------------------------------------------------------------------
# Unit: _run_deployment writes log_path to DB
# ---------------------------------------------------------------------------

class TestRunDeploymentLogging:
    """Test integrasi log writing di _run_deployment."""

    _patches: dict[str, str] = {
        "clone": "app.services.deployment_service.git_service.clone_repository",
        "cleanup": "app.services.deployment_service.git_service.cleanup",
        "run_compose": "app.services.deployment_service._run_compose",
        "write_env": "app.services.deployment_service._write_env_file",
        "update_status": "app.services.deployment_service.deployment_repository.update_status",
        "list_env": "app.services.deployment_service.env_var_repository.list_by_project",
        "health_check": "app.services.deployment_service.health_check_service.run_health_check",
        "make_log": "app.services.deployment_service._make_log_file",
        "append_log": "app.services.deployment_service._append_log",
    }

    def _clone_result(self) -> MagicMock:
        r = MagicMock()
        r.repo_dir = Path("/tmp/fake_repo")
        r.commit_sha = "abc12345"
        r.branch = "main"
        return r

    def _healthy_hc(self) -> MagicMock:
        from app.services.health_check import HealthCheckResult
        hc = MagicMock(spec=HealthCheckResult)
        hc.healthy = True
        hc.containers_checked = 1
        hc.message = "ok"
        return hc

    def test_log_path_stored_in_db(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]
        from app.models.application import Application
        from app.models.server import Server

        db = MagicMock()
        deployment = _make_mock_deployment()
        deployment.id = 42
        app = MagicMock(spec=Application)
        app.id = 1
        app.project_id = 1
        app.repository = "https://github.com/org/repo.git"
        app.branch = "main"
        app.compose_path = "docker-compose.yml"
        server = MagicMock(spec=Server)

        fake_log = tmp_path / "deployment_42.log"
        fake_log.touch()

        p = self._patches
        with (
            patch(p["make_log"], return_value=fake_log),
            patch(p["append_log"]),
            patch(p["clone"], return_value=self._clone_result()),
            patch(p["cleanup"]),
            patch(p["run_compose"], return_value=("ok", "")),
            patch(p["write_env"]),
            patch(p["list_env"], return_value=[]),
            patch(p["health_check"], return_value=self._healthy_hc()),
            patch(p["update_status"]) as mock_update,
        ):
            _run_deployment(db, deployment, app, server)

        # Cek ada panggilan update_status dengan log_path
        log_path_calls = [
            c for c in mock_update.call_args_list
            if c.kwargs.get("log_path") == str(fake_log)
        ]
        assert len(log_path_calls) >= 1

    def test_append_log_called_on_failure(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]
        from app.models.application import Application
        from app.models.server import Server

        db = MagicMock()
        deployment = _make_mock_deployment()
        deployment.id = 43
        app = MagicMock(spec=Application)
        app.id = 1
        app.project_id = 1
        app.repository = "https://github.com/org/repo.git"
        app.branch = "main"
        app.compose_path = "docker-compose.yml"
        server = MagicMock(spec=Server)

        fake_log = tmp_path / "deployment_43.log"
        fake_log.touch()

        p = self._patches
        with (
            patch(p["make_log"], return_value=fake_log),
            patch(p["append_log"]) as mock_append,
            patch(p["clone"], side_effect=RuntimeError("network error")),
            patch(p["cleanup"]),
            patch(p["update_status"]),
        ):
            with pytest.raises(RuntimeError):
                _run_deployment(db, deployment, app, server)

        # append_log dipanggil setidaknya satu kali dengan pesan error
        error_calls = [
            c for c in mock_append.call_args_list
            if "GAGAL" in str(c.args[1]) or "gagal" in str(c.args[1]).lower()
        ]
        assert len(error_calls) >= 1


# ---------------------------------------------------------------------------
# Unit: _wait_for_log_path
# ---------------------------------------------------------------------------

class TestWaitForLogPath:
    def test_returns_log_path_when_available(self, tmp_path: Path) -> None:
        from app.websocket.deployment_logs import _wait_for_log_path

        log_file = tmp_path / "deployment_1.log"
        log_file.touch()

        dep = _make_mock_deployment(log_path=str(log_file))
        db = MagicMock()

        with patch(
            "app.websocket.deployment_logs.deployment_repository.get_by_id",
            return_value=dep,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = asyncio.run(_wait_for_log_path(1, db, timeout=5.0))

        assert result == str(log_file)

    def test_returns_none_on_timeout(self) -> None:
        from app.websocket.deployment_logs import _wait_for_log_path

        dep = _make_mock_deployment(log_path=None, status=DeploymentStatus.deploying)
        db = MagicMock()

        with patch(
            "app.websocket.deployment_logs.deployment_repository.get_by_id",
            return_value=dep,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = asyncio.run(
                    _wait_for_log_path(1, db, timeout=0.1)
                )

        assert result is None

    def test_returns_immediately_for_terminal_without_log(self) -> None:
        from app.websocket.deployment_logs import _wait_for_log_path

        dep = _make_mock_deployment(log_path=None, status=DeploymentStatus.failed)
        db = MagicMock()

        with patch(
            "app.websocket.deployment_logs.deployment_repository.get_by_id",
            return_value=dep,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = asyncio.run(_wait_for_log_path(1, db, timeout=5.0))

        # Terminal status tanpa log → return None
        assert result is None


# ---------------------------------------------------------------------------
# Unit: _stream_log_file
# ---------------------------------------------------------------------------

class TestStreamLogFile:
    def test_streams_existing_lines(self, tmp_path: Path) -> None:
        from app.websocket.deployment_logs import _stream_log_file, DONE_SENTINEL

        log_file = tmp_path / "test.log"
        log_file.write_text("line one\nline two\n")

        sent_messages: list[str] = []

        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=lambda msg: sent_messages.append(msg))

        dep_success = _make_mock_deployment(status=DeploymentStatus.success)
        db = MagicMock()

        with patch(
            "app.websocket.deployment_logs.deployment_repository.get_by_id",
            return_value=dep_success,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                asyncio.run(_stream_log_file(ws, str(log_file), 1, db))

        assert "line one" in sent_messages
        assert "line two" in sent_messages
        assert DONE_SENTINEL in sent_messages

    def test_sends_done_sentinel_at_end(self, tmp_path: Path) -> None:
        from app.websocket.deployment_logs import _stream_log_file, DONE_SENTINEL

        log_file = tmp_path / "test.log"
        log_file.write_text("some log\n")

        sent: list[str] = []
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=lambda msg: sent.append(msg))

        dep = _make_mock_deployment(status=DeploymentStatus.success)
        db = MagicMock()

        with patch(
            "app.websocket.deployment_logs.deployment_repository.get_by_id",
            return_value=dep,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                asyncio.run(_stream_log_file(ws, str(log_file), 1, db))

        assert sent[-1] == DONE_SENTINEL

    def test_waits_when_deploying_then_exits_when_terminal(
        self, tmp_path: Path
    ) -> None:
        from app.websocket.deployment_logs import DONE_SENTINEL, _stream_log_file

        log_file = tmp_path / "test.log"
        log_file.write_text("building...\n")

        call_count = 0
        dep_deploying = _make_mock_deployment(status=DeploymentStatus.deploying)
        dep_success = _make_mock_deployment(status=DeploymentStatus.success)

        def get_dep_side_effect(_db: object, _dep_id: int) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return dep_deploying if call_count <= 2 else dep_success

        sent: list[str] = []
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=lambda msg: sent.append(msg))

        with patch(
            "app.websocket.deployment_logs.deployment_repository.get_by_id",
            side_effect=get_dep_side_effect,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                asyncio.run(_stream_log_file(ws, str(log_file), 1, db=MagicMock()))

        assert DONE_SENTINEL in sent

    def test_handles_websocket_disconnect_gracefully(self, tmp_path: Path) -> None:
        from fastapi.websockets import WebSocketDisconnect
        from app.websocket.deployment_logs import _stream_log_file

        log_file = tmp_path / "test.log"
        log_file.write_text("line\n")

        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=WebSocketDisconnect(code=1001))

        dep = _make_mock_deployment(status=DeploymentStatus.success)
        db = MagicMock()

        with patch(
            "app.websocket.deployment_logs.deployment_repository.get_by_id",
            return_value=dep,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Tidak boleh raise exception apapun
                asyncio.run(_stream_log_file(ws, str(log_file), 1, db))

    def test_strips_trailing_newline_from_lines(self, tmp_path: Path) -> None:
        from app.websocket.deployment_logs import _stream_log_file

        log_file = tmp_path / "test.log"
        log_file.write_text("hello world\n")

        sent: list[str] = []
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=lambda msg: sent.append(msg))

        dep = _make_mock_deployment(status=DeploymentStatus.success)
        db = MagicMock()

        with patch(
            "app.websocket.deployment_logs.deployment_repository.get_by_id",
            return_value=dep,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                asyncio.run(_stream_log_file(ws, str(log_file), 1, db))

        # Baris dikirim tanpa trailing newline
        assert "hello world" in sent
        assert "hello world\n" not in sent


# ---------------------------------------------------------------------------
# Integration: WebSocket endpoint via TestClient
# ---------------------------------------------------------------------------

def _register_and_login(client: TestClient) -> tuple[str, int]:
    """Register user baru, login, return (access_token, user_id)."""
    suffix = uuid.uuid4().hex[:8]
    user = {
        "username": f"ws_{suffix}",
        "email": f"ws_{suffix}@test.com",
        "password": "pass1234",
    }
    client.post("/auth/register", json=user)
    r = client.post(
        "/auth/login",
        data={"username": user["username"], "password": user["password"]},
    )
    data = r.json()["data"]
    token = data["access_token"]
    # Ambil user_id dari /users/me
    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    return token, user_id


def _create_project(client: TestClient, headers: dict[str, str]) -> int:
    suffix = uuid.uuid4().hex[:6]
    r = client.post(
        "/projects",
        json={"name": f"ws-proj-{suffix}", "description": "test"},
        headers=headers,
    )
    return int(r.json()["data"]["id"])


def _create_server(client: TestClient, headers: dict[str, str]) -> int:
    r = client.post(
        "/servers",
        json={
            "name": "ws-server",
            "host": "1.2.3.4",
            "port": 22,
            "username": "ubuntu",
            "auth_type": "password",
            "password": "secret",
        },
        headers=headers,
    )
    return int(r.json()["data"]["id"])


def _create_app(
    client: TestClient, headers: dict[str, str], project_id: int
) -> int:
    r = client.post(
        "/applications",
        json={
            "project_id": project_id,
            "name": "ws-app",
            "repository": "https://github.com/org/repo.git",
            "branch": "main",
        },
        headers=headers,
    )
    return int(r.json()["data"]["id"])


def _deploy_with_mocks(
    client: TestClient,
    headers: dict[str, str],
    app_id: int,
    server_id: int,
    log_path: str,
) -> int:
    """Trigger deployment dengan semua dep di-mock, termasuk log_path injeksi."""
    from app.services.health_check import HealthCheckResult

    clone_result = MagicMock()
    clone_result.repo_dir = Path("/tmp/fake_repo_ws")
    clone_result.commit_sha = "deadbeef12345678"

    healthy = HealthCheckResult(healthy=True, containers_checked=1, message="ok")

    with (
        patch(
            "app.services.deployment_service.git_service.clone_repository",
            return_value=clone_result,
        ),
        patch("app.services.deployment_service.git_service.cleanup"),
        patch(
            "app.services.deployment_service._run_compose",
            return_value=("ok", ""),
        ),
        patch(
            "app.services.deployment_service.health_check_service.run_health_check",
            return_value=healthy,
        ),
        patch(
            "app.services.deployment_service._make_log_file",
            return_value=Path(log_path),
        ),
        patch("app.services.deployment_service._append_log"),
    ):
        r = client.post(
            "/deployments",
            json={"application_id": app_id, "server_id": server_id},
            headers=headers,
        )
    return int(r.json()["data"]["id"])


class TestWebSocketEndpointAuth:
    """Test autentikasi dan otorisasi WebSocket endpoint."""

    def test_invalid_token_closes_with_error(self, client: TestClient) -> None:
        with client.websocket_connect(
            "/ws/deployments/1/logs?token=invalid_token_here"
        ) as ws:
            msg = ws.receive_text()
            assert "[INFRAFORGE:ERROR]" in msg

    def test_missing_token_returns_422(self, client: TestClient) -> None:
        # Tanpa query param token → FastAPI validasi gagal → HTTP 422 sebelum upgrade
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/deployments/1/logs"):
                pass

    def test_refresh_token_rejected(self, client: TestClient) -> None:
        """Refresh token tidak boleh digunakan untuk WebSocket."""
        suffix = uuid.uuid4().hex[:8]
        user = {
            "username": f"wsr_{suffix}",
            "email": f"wsr_{suffix}@test.com",
            "password": "pass1234",
        }
        client.post("/auth/register", json=user)
        r = client.post(
            "/auth/login",
            data={"username": user["username"], "password": user["password"]},
        )
        refresh_token = r.json()["data"]["refresh_token"]

        with client.websocket_connect(
            f"/ws/deployments/1/logs?token={refresh_token}"
        ) as ws:
            msg = ws.receive_text()
            assert "[INFRAFORGE:ERROR]" in msg


class TestWebSocketEndpointDeploymentNotFound:
    def test_unknown_deployment_returns_error(self, client: TestClient) -> None:
        token, _ = _register_and_login(client)
        with client.websocket_connect(
            f"/ws/deployments/99999/logs?token={token}"
        ) as ws:
            msg = ws.receive_text()
            assert "[INFRAFORGE:ERROR]" in msg

    def test_other_users_deployment_returns_access_denied(
        self, client: TestClient
    ) -> None:
        # User A buat deployment
        token_a, _ = _register_and_login(client)
        headers_a = {"Authorization": f"Bearer {token_a}"}
        project_id = _create_project(client, headers_a)
        server_id = _create_server(client, headers_a)
        app_id = _create_app(client, headers_a, project_id)

        with tempfile.NamedTemporaryFile(
            suffix=".log", delete=False, mode="w"
        ) as f:
            f.write("[InfraForge] test log\n")
            log_path = f.name

        dep_id = _deploy_with_mocks(
            client, headers_a, app_id, server_id, log_path
        )

        # User B coba akses → harus ditolak
        token_b, _ = _register_and_login(client)
        with client.websocket_connect(
            f"/ws/deployments/{dep_id}/logs?token={token_b}"
        ) as ws:
            msg = ws.receive_text()
            assert "[INFRAFORGE:ERROR]" in msg


class TestWebSocketEndpointStreaming:
    """Test streaming log via WebSocket dengan log file nyata."""

    def test_streams_log_and_sends_done_sentinel(
        self, client: TestClient, db_session: object
    ) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.websocket.deployment_logs import DONE_SENTINEL
        from app.repositories import deployment_repository

        token, _ = _register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        project_id = _create_project(client, headers)
        server_id = _create_server(client, headers)
        app_id = _create_app(client, headers, project_id)

        # Buat log file nyata dengan isi
        with tempfile.NamedTemporaryFile(
            suffix=".log", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write("[InfraForge] Deployment dimulai.\n")
            f.write("[InfraForge] Clone selesai.\n")
            f.write("[InfraForge] Deployment SUKSES.\n")
            log_path = f.name

        dep_id = _deploy_with_mocks(
            client, headers, app_id, server_id, log_path
        )

        # Update log_path via db_session yang sama dengan client fixture
        db: SASession = db_session  # type: ignore[assignment]
        dep = deployment_repository.get_by_id(db, dep_id)
        assert dep is not None
        dep.log_path = log_path
        db.commit()

        received: list[str] = []
        # Mock _get_db_session agar WebSocket handler pakai session yang sama
        with patch(
            "app.websocket.deployment_logs._get_db_session",
            return_value=db,
        ):
            with client.websocket_connect(
                f"/ws/deployments/{dep_id}/logs?token={token}"
            ) as ws:
                while True:
                    try:
                        msg = ws.receive_text()
                        received.append(msg)
                        if msg == DONE_SENTINEL:
                            break
                    except Exception:
                        break

        assert any("[InfraForge]" in m for m in received)
        assert DONE_SENTINEL in received

    def test_deployment_without_log_path_sends_done(
        self, client: TestClient, db_session: object
    ) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.websocket.deployment_logs import DONE_SENTINEL
        from app.repositories import deployment_repository
        from app.services.health_check import HealthCheckResult

        token, _ = _register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        project_id = _create_project(client, headers)
        server_id = _create_server(client, headers)
        app_id = _create_app(client, headers, project_id)

        clone_result = MagicMock()
        clone_result.repo_dir = Path("/tmp/fake_nolog")
        clone_result.commit_sha = "abc123"

        healthy = HealthCheckResult(healthy=True, containers_checked=1, message="ok")

        with (
            patch(
                "app.services.deployment_service.git_service.clone_repository",
                return_value=clone_result,
            ),
            patch("app.services.deployment_service.git_service.cleanup"),
            patch(
                "app.services.deployment_service._run_compose",
                return_value=("ok", ""),
            ),
            patch(
                "app.services.deployment_service.health_check_service.run_health_check",
                return_value=healthy,
            ),
            patch(
                "app.services.deployment_service._make_log_file",
                return_value=Path("/tmp/deployment_nolog.log"),
            ),
            patch("app.services.deployment_service._append_log"),
        ):
            r = client.post(
                "/deployments",
                json={"application_id": app_id, "server_id": server_id},
                headers=headers,
            )
        dep_id = r.json()["data"]["id"]

        # Paksa log_path = None via db_session yang sama dengan client fixture
        db: SASession = db_session  # type: ignore[assignment]
        dep = deployment_repository.get_by_id(db, dep_id)
        assert dep is not None
        dep.log_path = None
        dep.status = DeploymentStatus.success
        db.commit()

        received: list[str] = []
        # Mock _get_db_session agar WebSocket handler pakai session yang sama
        with patch(
            "app.websocket.deployment_logs._get_db_session",
            return_value=db,
        ):
            with client.websocket_connect(
                f"/ws/deployments/{dep_id}/logs?token={token}"
            ) as ws:
                while True:
                    try:
                        msg = ws.receive_text()
                        received.append(msg)
                        if msg == DONE_SENTINEL:
                            break
                    except Exception:
                        break

        assert DONE_SENTINEL in received


# ---------------------------------------------------------------------------
# Unit: DONE_SENTINEL constant
# ---------------------------------------------------------------------------

class TestDoneSentinel:
    def test_sentinel_value(self) -> None:
        from app.websocket.deployment_logs import DONE_SENTINEL

        assert DONE_SENTINEL == "[INFRAFORGE:DONE]"

    def test_poll_interval_positive(self) -> None:
        from app.websocket.deployment_logs import POLL_INTERVAL

        assert POLL_INTERVAL > 0


# ---------------------------------------------------------------------------
# Unit: _get_db_session
# ---------------------------------------------------------------------------

class TestGetDbSession:
    def test_returns_session(self) -> None:
        from app.websocket.deployment_logs import _get_db_session
        from sqlalchemy.orm import Session

        db = _get_db_session()
        try:
            assert isinstance(db, Session)
        finally:
            db.close()
