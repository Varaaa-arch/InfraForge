"""
Unit test untuk Task 3.6 — Deployment Flow.

Semua test menggunakan mock untuk:
- git_service (clone, cleanup)
- _run_compose (subprocess docker compose)
- _write_env_file
- encryption_service.decrypt

Sehingga test tidak butuh koneksi internet, Docker daemon, atau Git.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.deployment import DeploymentStatus


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def _make_app(
    app_id: int = 1,
    project_id: int = 1,
    repository: str | None = "https://github.com/org/repo.git",
    branch: str = "main",
    compose_path: str = "docker-compose.yml",
) -> MagicMock:
    app = MagicMock()
    app.id = app_id
    app.project_id = project_id
    app.repository = repository
    app.branch = branch
    app.compose_path = compose_path
    return app


def _make_server(server_id: int = 1) -> MagicMock:
    server = MagicMock()
    server.id = server_id
    return server


def _make_deployment(
    dep_id: int = 10,
    application_id: int = 1,
    server_id: int | None = 1,
    branch: str = "main",
    status: DeploymentStatus = DeploymentStatus.pending,
    commit_sha: str | None = None,
) -> MagicMock:
    dep = MagicMock()
    dep.id = dep_id
    dep.application_id = application_id
    dep.server_id = server_id
    dep.branch = branch
    dep.status = status
    dep.commit_sha = commit_sha
    dep.log_path = None
    dep.started_at = datetime.now(tz=timezone.utc)
    dep.finished_at = None
    return dep


def _make_clone_result(sha: str = "deadbeef1234abcd") -> MagicMock:
    result = MagicMock()
    result.repo_dir = Path("/tmp/fake_clone_dir")
    result.branch = "main"
    result.commit_sha = sha
    result.success = True
    return result


# ---------------------------------------------------------------------------
# _write_env_file
# ---------------------------------------------------------------------------

class TestWriteEnvFile:
    def test_writes_key_value_pairs(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _write_env_file  # type: ignore[attr-defined]

        env_vars = {"DATABASE_URL": "postgres://localhost/db", "SECRET_KEY": "abc123"}
        env_file = _write_env_file(tmp_path, env_vars)

        content = env_file.read_text()
        assert "DATABASE_URL=postgres://localhost/db" in content
        assert "SECRET_KEY=abc123" in content

    def test_returns_path_to_dotenv(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _write_env_file  # type: ignore[attr-defined]

        result = _write_env_file(tmp_path, {"KEY": "val"})
        assert result.name == ".env"
        assert result.parent == tmp_path

    def test_empty_env_vars_creates_empty_file(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _write_env_file  # type: ignore[attr-defined]

        env_file = _write_env_file(tmp_path, {})
        assert env_file.read_text() == ""


# ---------------------------------------------------------------------------
# _run_compose
# ---------------------------------------------------------------------------

class TestRunCompose:
    def test_calls_build_and_up(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _run_compose  # type: ignore[attr-defined]

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _run_compose(tmp_path, "docker-compose.yml")

        assert mock_run.call_count == 2
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("build" in c for c in calls)
        assert any("up" in c for c in calls)

    def test_raises_runtime_error_on_nonzero_exit(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _run_compose  # type: ignore[attr-defined]

        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stdout = ""
        fail_result.stderr = "image build failed"

        with patch("subprocess.run", return_value=fail_result):
            with pytest.raises(RuntimeError, match="gagal"):
                _run_compose(tmp_path, "docker-compose.yml")

    def test_passes_compose_file_to_command(self, tmp_path: Path) -> None:
        from app.services.deployment_service import _run_compose  # type: ignore[attr-defined]

        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = ""
        ok.stderr = ""

        with patch("subprocess.run", return_value=ok) as mock_run:
            _run_compose(tmp_path, "infra/compose.prod.yml")

        for call in mock_run.call_args_list:
            assert "infra/compose.prod.yml" in call.args[0]


# ---------------------------------------------------------------------------
# _run_deployment (orchestration unit tests — all dependencies mocked)
# ---------------------------------------------------------------------------

class TestRunDeployment:
    """Test orkestrasi _run_deployment dengan semua dependensi di-mock."""

    def _patches(self) -> dict[str, str]:
        return {
            "clone": "app.services.deployment_service.git_service.clone_repository",
            "cleanup": "app.services.deployment_service.git_service.cleanup",
            "run_compose": "app.services.deployment_service._run_compose",
            "write_env": "app.services.deployment_service._write_env_file",
            "update_status": "app.services.deployment_service.deployment_repository.update_status",
            "list_env": "app.services.deployment_service.env_var_repository.list_by_project",
            "decrypt": "app.services.deployment_service.encryption_service.decrypt",
            "health_check": "app.services.deployment_service.health_check_service.run_health_check",
        }

    def _healthy_hc(self) -> MagicMock:
        from app.services.health_check import HealthCheckResult
        r = MagicMock(spec=HealthCheckResult)
        r.healthy = True
        r.containers_checked = 1
        r.message = "ok"
        return r

    def test_success_flow_updates_status_to_success(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()
        clone_result = _make_clone_result()

        p = self._patches()
        with (
            patch(p["clone"], return_value=clone_result),
            patch(p["cleanup"]),
            patch(p["run_compose"], return_value=("build ok", "")),
            patch(p["write_env"]),
            patch(p["list_env"], return_value=[]),
            patch(p["health_check"], return_value=self._healthy_hc()),
            patch(p["update_status"]) as mock_update,
        ):
            _run_deployment(db, deployment, app, server)

        statuses = [call.args[2] for call in mock_update.call_args_list]
        assert DeploymentStatus.success in statuses

    def test_clone_failure_sets_status_failed_and_reraises(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()

        p = self._patches()
        with (
            patch(p["clone"], side_effect=RuntimeError("network error")),
            patch(p["cleanup"]),
            patch(p["update_status"]) as mock_update,
        ):
            with pytest.raises(RuntimeError, match="Deployment gagal"):
                _run_deployment(db, deployment, app, server)

        statuses = [call.args[2] for call in mock_update.call_args_list]
        assert DeploymentStatus.failed in statuses

    def test_compose_failure_sets_status_failed(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()
        clone_result = _make_clone_result()

        p = self._patches()
        with (
            patch(p["clone"], return_value=clone_result),
            patch(p["cleanup"]),
            patch(p["run_compose"], side_effect=RuntimeError("build failed")),
            patch(p["write_env"]),
            patch(p["list_env"], return_value=[]),
            patch(p["update_status"]) as mock_update,
        ):
            with pytest.raises(RuntimeError):
                _run_deployment(db, deployment, app, server)

        statuses = [call.args[2] for call in mock_update.call_args_list]
        assert DeploymentStatus.failed in statuses

    def test_cleanup_always_called_on_success(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()
        clone_result = _make_clone_result()

        p = self._patches()
        with (
            patch(p["clone"], return_value=clone_result),
            patch(p["cleanup"]) as mock_cleanup,
            patch(p["run_compose"], return_value=("", "")),
            patch(p["write_env"]),
            patch(p["list_env"], return_value=[]),
            patch(p["health_check"], return_value=self._healthy_hc()),
            patch(p["update_status"]),
        ):
            _run_deployment(db, deployment, app, server)

        mock_cleanup.assert_called_once_with(clone_result.repo_dir)

    def test_cleanup_always_called_on_failure(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()
        clone_result = _make_clone_result()

        p = self._patches()
        with (
            patch(p["clone"], return_value=clone_result),
            patch(p["cleanup"]) as mock_cleanup,
            patch(p["run_compose"], side_effect=RuntimeError("oops")),
            patch(p["write_env"]),
            patch(p["list_env"], return_value=[]),
            patch(p["update_status"]),
        ):
            with pytest.raises(RuntimeError):
                _run_deployment(db, deployment, app, server)

        mock_cleanup.assert_called_once_with(clone_result.repo_dir)

    def test_no_repository_raises_before_clone(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app(repository=None)
        server = _make_server()
        deployment = _make_deployment()

        p = self._patches()
        with (
            patch(p["clone"]) as mock_clone,
            patch(p["cleanup"]),
            patch(p["update_status"]),
        ):
            with pytest.raises(RuntimeError, match="Deployment gagal"):
                _run_deployment(db, deployment, app, server)

        mock_clone.assert_not_called()

    def test_env_vars_written_when_present(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()
        clone_result = _make_clone_result()

        mock_ev = MagicMock()
        mock_ev.key = "DB_URL"
        mock_ev.encrypted_value = "encrypted_val"

        p = self._patches()
        with (
            patch(p["clone"], return_value=clone_result),
            patch(p["cleanup"]),
            patch(p["run_compose"], return_value=("", "")),
            patch(p["write_env"]) as mock_write,
            patch(p["list_env"], return_value=[mock_ev]),
            patch(p["decrypt"], return_value="postgres://localhost/db"),
            patch(p["health_check"], return_value=self._healthy_hc()),
            patch(p["update_status"]),
        ):
            _run_deployment(db, deployment, app, server)

        mock_write.assert_called_once()
        written_env = mock_write.call_args.args[1]
        assert written_env["DB_URL"] == "postgres://localhost/db"

    def test_no_env_file_written_when_no_env_vars(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()
        clone_result = _make_clone_result()

        p = self._patches()
        with (
            patch(p["clone"], return_value=clone_result),
            patch(p["cleanup"]),
            patch(p["run_compose"], return_value=("", "")),
            patch(p["write_env"]) as mock_write,
            patch(p["list_env"], return_value=[]),
            patch(p["health_check"], return_value=self._healthy_hc()),
            patch(p["update_status"]),
        ):
            _run_deployment(db, deployment, app, server)

        mock_write.assert_not_called()

    def test_commit_sha_stored_after_clone(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()
        clone_result = _make_clone_result(sha="cafebabe12345678")

        p = self._patches()
        with (
            patch(p["clone"], return_value=clone_result),
            patch(p["cleanup"]),
            patch(p["run_compose"], return_value=("", "")),
            patch(p["write_env"]),
            patch(p["list_env"], return_value=[]),
            patch(p["health_check"], return_value=self._healthy_hc()),
            patch(p["update_status"]) as mock_update,
        ):
            _run_deployment(db, deployment, app, server)

        # Cari panggilan update_status yang menyertakan commit_sha
        sha_calls = [
            c for c in mock_update.call_args_list
            if c.kwargs.get("commit_sha") == "cafebabe12345678"
        ]
        assert len(sha_calls) >= 1


# ---------------------------------------------------------------------------
# trigger_deployment
# ---------------------------------------------------------------------------

class TestTriggerDeployment:
    def test_raises_value_error_when_app_not_found(self) -> None:
        from app.services.deployment_service import trigger_deployment

        db = MagicMock()
        with patch(
            "app.services.deployment_service.application_repository.get_by_id",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="Application tidak ditemukan"):
                trigger_deployment(db, application_id=99, server_id=1)

    def test_raises_value_error_when_server_not_found(self) -> None:
        from app.services.deployment_service import trigger_deployment

        db = MagicMock()
        with (
            patch(
                "app.services.deployment_service.application_repository.get_by_id",
                return_value=_make_app(),
            ),
            patch(
                "app.services.deployment_service.server_repository.get_by_id",
                return_value=None,
            ),
        ):
            with pytest.raises(ValueError, match="Server tidak ditemukan"):
                trigger_deployment(db, application_id=1, server_id=99)

    def test_branch_override_used_when_provided(self) -> None:
        from app.services.deployment_service import trigger_deployment

        db = MagicMock()
        app = _make_app(branch="main")
        server = _make_server()
        deployment = _make_deployment(branch="feature/x")

        with (
            patch(
                "app.services.deployment_service.application_repository.get_by_id",
                return_value=app,
            ),
            patch(
                "app.services.deployment_service.server_repository.get_by_id",
                return_value=server,
            ),
            patch(
                "app.services.deployment_service.deployment_repository.create",
                return_value=deployment,
            ) as mock_create,
            patch("app.services.deployment_service._run_deployment"),
        ):
            trigger_deployment(
                db, application_id=1, server_id=1, branch_override="feature/x"
            )

        assert mock_create.call_args.args[3] == "feature/x"

    def test_app_branch_used_when_no_override(self) -> None:
        from app.services.deployment_service import trigger_deployment

        db = MagicMock()
        app = _make_app(branch="develop")
        server = _make_server()
        deployment = _make_deployment(branch="develop")

        with (
            patch(
                "app.services.deployment_service.application_repository.get_by_id",
                return_value=app,
            ),
            patch(
                "app.services.deployment_service.server_repository.get_by_id",
                return_value=server,
            ),
            patch(
                "app.services.deployment_service.deployment_repository.create",
                return_value=deployment,
            ) as mock_create,
            patch("app.services.deployment_service._run_deployment"),
        ):
            trigger_deployment(db, application_id=1, server_id=1)

        assert mock_create.call_args.args[3] == "develop"

    def test_returns_deployment_object(self) -> None:
        from app.services.deployment_service import trigger_deployment

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        expected = _make_deployment()

        with (
            patch(
                "app.services.deployment_service.application_repository.get_by_id",
                return_value=app,
            ),
            patch(
                "app.services.deployment_service.server_repository.get_by_id",
                return_value=server,
            ),
            patch(
                "app.services.deployment_service.deployment_repository.create",
                return_value=expected,
            ),
            patch("app.services.deployment_service._run_deployment"),
        ):
            result = trigger_deployment(db, application_id=1, server_id=1)

        assert result is expected


# ---------------------------------------------------------------------------
# API endpoint integration tests
# ---------------------------------------------------------------------------

class TestDeploymentEndpoints:
    """Test endpoint HTTP — pakai TestClient + DB rollback dari conftest."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _register_and_login(self, client: object) -> dict[str, str]:
        import uuid
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        suffix = uuid.uuid4().hex[:8]
        user = {
            "username": f"dep_{suffix}",
            "email": f"dep_{suffix}@x.com",
            "password": "pass1234",
        }
        c.post("/auth/register", json=user)
        r = c.post(
            "/auth/login",
            data={"username": user["username"], "password": user["password"]},
        )
        token = r.json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def _create_project(self, client: object, headers: dict[str, str]) -> int:
        import uuid
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.post(
            "/projects",
            json={"name": f"proj-{uuid.uuid4().hex[:6]}", "description": "test"},
            headers=headers,
        )
        return int(r.json()["data"]["id"])

    def _create_server(self, client: object, headers: dict[str, str]) -> int:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.post(
            "/servers",
            json={
                "name": "test-server",
                "host": "192.168.1.1",
                "port": 22,
                "username": "ubuntu",
                "auth_type": "password",
                "password": "secret",
            },
            headers=headers,
        )
        return int(r.json()["data"]["id"])

    def _create_app(
        self, client: object, headers: dict[str, str], project_id: int
    ) -> int:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.post(
            "/applications",
            json={
                "project_id": project_id,
                "name": "test-app",
                "repository": "https://github.com/org/repo.git",
                "branch": "main",
            },
            headers=headers,
        )
        return int(r.json()["data"]["id"])

    # ------------------------------------------------------------------
    # POST /deployments
    # ------------------------------------------------------------------

    def test_trigger_deployment_success_returns_201(self, client: object) -> None:
        from fastapi.testclient import TestClient
        from app.services.health_check import HealthCheckResult
        c: TestClient = client  # type: ignore[assignment]
        headers = self._register_and_login(c)
        project_id = self._create_project(c, headers)
        server_id = self._create_server(c, headers)
        app_id = self._create_app(c, headers, project_id)

        clone_result = _make_clone_result()
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
        ):
            r = c.post(
                "/deployments",
                json={"application_id": app_id, "server_id": server_id},
                headers=headers,
            )

        assert r.status_code == 201
        data = r.json()["data"]
        assert data["application_id"] == app_id
        assert data["status"] == "success"

    def test_trigger_deployment_without_auth_returns_401(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.post("/deployments", json={"application_id": 1, "server_id": 1})
        assert r.status_code == 401

    def test_trigger_deployment_unknown_app_returns_404(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._register_and_login(c)
        r = c.post(
            "/deployments",
            json={"application_id": 99999, "server_id": 1},
            headers=headers,
        )
        assert r.status_code == 404

    def test_trigger_deployment_compose_failure_returns_500(
        self, client: object
    ) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._register_and_login(c)
        project_id = self._create_project(c, headers)
        server_id = self._create_server(c, headers)
        app_id = self._create_app(c, headers, project_id)

        clone_result = _make_clone_result()
        with (
            patch(
                "app.services.deployment_service.git_service.clone_repository",
                return_value=clone_result,
            ),
            patch("app.services.deployment_service.git_service.cleanup"),
            patch(
                "app.services.deployment_service._run_compose",
                side_effect=RuntimeError("build failed"),
            ),
        ):
            r = c.post(
                "/deployments",
                json={"application_id": app_id, "server_id": server_id},
                headers=headers,
            )

        assert r.status_code == 500

    def test_trigger_deployment_with_branch_override(self, client: object) -> None:
        from fastapi.testclient import TestClient
        from app.services.health_check import HealthCheckResult
        c: TestClient = client  # type: ignore[assignment]
        headers = self._register_and_login(c)
        project_id = self._create_project(c, headers)
        server_id = self._create_server(c, headers)
        app_id = self._create_app(c, headers, project_id)

        clone_result = _make_clone_result()
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
        ):
            r = c.post(
                "/deployments",
                json={
                    "application_id": app_id,
                    "server_id": server_id,
                    "branch": "feature/new-ui",
                },
                headers=headers,
            )

        assert r.status_code == 201
        assert r.json()["data"]["branch"] == "feature/new-ui"

    # ------------------------------------------------------------------
    # GET /deployments
    # ------------------------------------------------------------------

    def test_list_deployments_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._register_and_login(c)
        r = c.get("/deployments", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_list_deployments_without_auth_returns_401(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.get("/deployments")
        assert r.status_code == 401

    def test_list_deployments_filter_by_app_id(self, client: object) -> None:
        from fastapi.testclient import TestClient
        from app.services.health_check import HealthCheckResult
        c: TestClient = client  # type: ignore[assignment]
        headers = self._register_and_login(c)
        project_id = self._create_project(c, headers)
        server_id = self._create_server(c, headers)
        app_id = self._create_app(c, headers, project_id)

        clone_result = _make_clone_result()
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
        ):
            c.post(
                "/deployments",
                json={"application_id": app_id, "server_id": server_id},
                headers=headers,
            )

        r = c.get(f"/deployments?application_id={app_id}", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) >= 1
        assert all(d["application_id"] == app_id for d in data)

    def test_list_deployments_unknown_app_filter_returns_404(
        self, client: object
    ) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._register_and_login(c)
        r = c.get("/deployments?application_id=99999", headers=headers)
        assert r.status_code == 404

    # ------------------------------------------------------------------
    # GET /deployments/{id}
    # ------------------------------------------------------------------

    def test_get_deployment_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        from app.services.health_check import HealthCheckResult
        c: TestClient = client  # type: ignore[assignment]
        headers = self._register_and_login(c)
        project_id = self._create_project(c, headers)
        server_id = self._create_server(c, headers)
        app_id = self._create_app(c, headers, project_id)

        clone_result = _make_clone_result()
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
        ):
            created = c.post(
                "/deployments",
                json={"application_id": app_id, "server_id": server_id},
                headers=headers,
            )

        dep_id = created.json()["data"]["id"]
        r = c.get(f"/deployments/{dep_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["id"] == dep_id

    def test_get_deployment_not_found_returns_404(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._register_and_login(c)
        r = c.get("/deployments/99999", headers=headers)
        assert r.status_code == 404

    def test_get_deployment_without_auth_returns_401(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.get("/deployments/1")
        assert r.status_code == 401

    def test_get_deployment_other_user_returns_404(self, client: object) -> None:
        """User lain tidak boleh bisa melihat deployment milik user pertama."""
        from fastapi.testclient import TestClient
        from app.services.health_check import HealthCheckResult
        c: TestClient = client  # type: ignore[assignment]

        # User A buat deployment
        headers_a = self._register_and_login(c)
        project_id = self._create_project(c, headers_a)
        server_id = self._create_server(c, headers_a)
        app_id = self._create_app(c, headers_a, project_id)

        clone_result = _make_clone_result()
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
        ):
            created = c.post(
                "/deployments",
                json={"application_id": app_id, "server_id": server_id},
                headers=headers_a,
            )
        dep_id = created.json()["data"]["id"]

        # User B coba akses
        headers_b = self._register_and_login(c)
        r = c.get(f"/deployments/{dep_id}", headers=headers_b)
        assert r.status_code == 404


# ==========================================================================
# Task 3.7 — Tests tambahan: filter, pagination, duration, commit_sha
# ==========================================================================

# ---------------------------------------------------------------------------
# Repository — filter & pagination unit tests
# ---------------------------------------------------------------------------

class TestDeploymentRepositoryFilter:
    """
    Test repository layer filter & pagination.

    Menggunakan deployment_service.trigger_deployment (dengan mock) via
    TestClient agar FK constraints (application_id, server_id) terpenuhi,
    lalu query langsung ke repository untuk validasi filter/pagination.
    """

    def _setup(self, client: object) -> tuple[dict[str, str], int, int]:
        """Buat user, project, server, app — return (headers, app_id, server_id)."""
        import uuid
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        suffix = uuid.uuid4().hex[:8]
        user = {"username": f"rep_{suffix}", "email": f"rep_{suffix}@x.com", "password": "pass1234"}
        c.post("/auth/register", json=user)
        r = c.post("/auth/login", data={"username": user["username"], "password": user["password"]})
        headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
        proj_id = c.post("/projects", json={"name": f"p{suffix}", "description": "t"}, headers=headers).json()["data"]["id"]
        srv_id = c.post("/servers", json={"name": "s", "host": "1.2.3.4", "port": 22, "username": "u", "auth_type": "password", "password": "x"}, headers=headers).json()["data"]["id"]
        app_id = c.post("/applications", json={"project_id": proj_id, "name": "a", "repository": "https://github.com/org/repo.git", "branch": "main"}, headers=headers).json()["data"]["id"]
        return headers, app_id, srv_id

    def _deploy(self, client: object, headers: dict[str, str], app_id: int, server_id: int) -> int:
        """Trigger deployment via API (mocked), kembalikan deployment id."""
        from fastapi.testclient import TestClient
        from app.services.health_check import HealthCheckResult
        c: TestClient = client  # type: ignore[assignment]
        clone_result = _make_clone_result()
        healthy = HealthCheckResult(healthy=True, containers_checked=1, message="ok")
        with (
            patch("app.services.deployment_service.git_service.clone_repository", return_value=clone_result),
            patch("app.services.deployment_service.git_service.cleanup"),
            patch("app.services.deployment_service._run_compose", return_value=("ok", "")),
            patch("app.services.deployment_service.health_check_service.run_health_check", return_value=healthy),
        ):
            r = c.post("/deployments", json={"application_id": app_id, "server_id": server_id}, headers=headers)
        return int(r.json()["data"]["id"])

    def test_list_all_returns_only_owned_app_ids(self, client: object, db_session: object) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        headers, app_id, srv_id = self._setup(client)
        self._deploy(client, headers, app_id, srv_id)

        db: SASession = db_session  # type: ignore[assignment]
        result = deployment_repository.list_all(db, [app_id])
        assert all(d.application_id == app_id for d in result)  # type: ignore[union-attr]

    def test_list_all_filter_by_status_success(self, client: object, db_session: object) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        headers, app_id, srv_id = self._setup(client)
        self._deploy(client, headers, app_id, srv_id)

        db: SASession = db_session  # type: ignore[assignment]
        result = deployment_repository.list_all(db, [app_id], status=DeploymentStatus.success)
        assert len(result) >= 1
        assert all(d.status == DeploymentStatus.success for d in result)  # type: ignore[union-attr]

    def test_list_all_filter_by_status_failed_returns_empty(self, client: object, db_session: object) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        headers, app_id, srv_id = self._setup(client)
        self._deploy(client, headers, app_id, srv_id)

        db: SASession = db_session  # type: ignore[assignment]
        result = deployment_repository.list_all(db, [app_id], status=DeploymentStatus.failed)
        assert result == []

    def test_list_all_filter_by_server_id(self, client: object, db_session: object) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        headers, app_id, srv_id = self._setup(client)
        self._deploy(client, headers, app_id, srv_id)

        db: SASession = db_session  # type: ignore[assignment]
        result = deployment_repository.list_all(db, [app_id], server_id=srv_id)
        assert all(d.server_id == srv_id for d in result)  # type: ignore[union-attr]

    def test_list_all_pagination_limit(self, client: object, db_session: object) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        headers, app_id, srv_id = self._setup(client)
        for _ in range(3):
            self._deploy(client, headers, app_id, srv_id)

        db: SASession = db_session  # type: ignore[assignment]
        result = deployment_repository.list_all(db, [app_id], limit=2)
        assert len(result) == 2

    def test_list_all_pagination_offset(self, client: object, db_session: object) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        headers, app_id, srv_id = self._setup(client)
        for _ in range(3):
            self._deploy(client, headers, app_id, srv_id)

        db: SASession = db_session  # type: ignore[assignment]
        all_r = deployment_repository.list_all(db, [app_id], limit=10, offset=0)
        off_r = deployment_repository.list_all(db, [app_id], limit=10, offset=1)
        assert len(off_r) == len(all_r) - 1

    def test_list_all_empty_when_no_app_ids(self, db_session: object) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        db: SASession = db_session  # type: ignore[assignment]
        assert deployment_repository.list_all(db, []) == []

    def test_list_by_application_filter_status(self, client: object, db_session: object) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        headers, app_id, srv_id = self._setup(client)
        self._deploy(client, headers, app_id, srv_id)

        db: SASession = db_session  # type: ignore[assignment]
        result = deployment_repository.list_by_application(db, app_id, status=DeploymentStatus.success)
        assert len(result) >= 1
        assert all(d.status == DeploymentStatus.success for d in result)  # type: ignore[union-attr]

    def test_list_by_application_pagination(self, client: object, db_session: object) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        headers, app_id, srv_id = self._setup(client)
        for _ in range(4):
            self._deploy(client, headers, app_id, srv_id)

        db: SASession = db_session  # type: ignore[assignment]
        page1 = deployment_repository.list_by_application(db, app_id, limit=2, offset=0)
        page2 = deployment_repository.list_by_application(db, app_id, limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        ids1 = {d.id for d in page1}  # type: ignore[union-attr]
        ids2 = {d.id for d in page2}  # type: ignore[union-attr]
        assert ids1.isdisjoint(ids2)

    def test_update_status_sets_finished_at_and_commit_sha(self, client: object, db_session: object) -> None:
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        headers, app_id, srv_id = self._setup(client)
        dep_id = self._deploy(client, headers, app_id, srv_id)

        db: SASession = db_session  # type: ignore[assignment]
        dep = deployment_repository.get_by_id(db, dep_id)
        assert dep is not None
        assert dep.finished_at is not None   # success → finished_at diset
        assert dep.commit_sha is not None    # clone_result.commit_sha disimpan

    def test_update_status_no_finished_at_for_deploying(self, client: object, db_session: object) -> None:
        """Saat status masih deploying, finished_at harus None."""
        from sqlalchemy.orm import Session as SASession
        from app.repositories import deployment_repository
        headers, app_id, srv_id = self._setup(client)

        db: SASession = db_session  # type: ignore[assignment]
        # Buat deployment pending, lalu set deploying (non-terminal)
        dep = deployment_repository.create(db, app_id, srv_id, "main")
        updated = deployment_repository.update_status(db, dep, DeploymentStatus.deploying)
        assert updated.finished_at is None


# ---------------------------------------------------------------------------
# Schema — duration computed field
# ---------------------------------------------------------------------------

class TestDeploymentResponseDuration:
    def test_duration_computed_when_finished_at_set(self) -> None:
        from datetime import timezone
        from app.schemas.deployment import DeploymentResponse

        now = datetime.now(tz=timezone.utc)
        started = now.replace(second=0, microsecond=0)
        finished = started.replace(second=30)

        resp = DeploymentResponse(
            id=1,
            application_id=1,
            server_id=1,
            status=DeploymentStatus.success,
            branch="main",
            commit_sha="abc123",
            log_path=None,
            started_at=started,
            finished_at=finished,
        )
        assert resp.duration == 30.0

    def test_duration_none_when_not_finished(self) -> None:
        from datetime import timezone
        from app.schemas.deployment import DeploymentResponse

        resp = DeploymentResponse(
            id=1,
            application_id=1,
            server_id=None,
            status=DeploymentStatus.deploying,
            branch="main",
            commit_sha=None,
            log_path=None,
            started_at=datetime.now(tz=timezone.utc),
            finished_at=None,
        )
        assert resp.duration is None

    def test_duration_sub_second_precision(self) -> None:
        from datetime import timedelta, timezone
        from app.schemas.deployment import DeploymentResponse

        started = datetime.now(tz=timezone.utc)
        finished = started + timedelta(seconds=123, milliseconds=456)

        resp = DeploymentResponse(
            id=1,
            application_id=1,
            server_id=1,
            status=DeploymentStatus.success,
            branch="main",
            commit_sha=None,
            log_path=None,
            started_at=started,
            finished_at=finished,
        )
        assert resp.duration == pytest.approx(123.456, abs=0.01)


# ---------------------------------------------------------------------------
# API endpoint — filter & pagination integration tests
# ---------------------------------------------------------------------------

class TestDeploymentEndpointsFilter:
    """Test endpoint HTTP untuk fitur filter & pagination Task 3.7."""

    def _setup(self, client: object) -> tuple[dict[str, str], int, int, int]:
        """
        Buat user, project, server, app — kembalikan
        (headers, server_id, app_id, project_id).
        """
        import uuid
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]

        suffix = uuid.uuid4().hex[:8]
        user = {
            "username": f"flt_{suffix}",
            "email": f"flt_{suffix}@x.com",
            "password": "pass1234",
        }
        c.post("/auth/register", json=user)
        r = c.post(
            "/auth/login",
            data={"username": user["username"], "password": user["password"]},
        )
        headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

        proj_r = c.post(
            "/projects",
            json={"name": f"p-{suffix}", "description": "t"},
            headers=headers,
        )
        project_id = proj_r.json()["data"]["id"]

        srv_r = c.post(
            "/servers",
            json={
                "name": "srv",
                "host": "1.2.3.4",
                "port": 22,
                "username": "ubuntu",
                "auth_type": "password",
                "password": "x",
            },
            headers=headers,
        )
        server_id = srv_r.json()["data"]["id"]

        app_r = c.post(
            "/applications",
            json={
                "project_id": project_id,
                "name": "myapp",
                "repository": "https://github.com/org/repo.git",
                "branch": "main",
            },
            headers=headers,
        )
        app_id = app_r.json()["data"]["id"]
        return headers, server_id, app_id, project_id

    def _deploy(
        self, client: object, headers: dict[str, str], app_id: int, server_id: int
    ) -> dict[str, object]:
        from fastapi.testclient import TestClient
        from app.services.health_check import HealthCheckResult
        c: TestClient = client  # type: ignore[assignment]
        clone_result = _make_clone_result()
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
        ):
            r = c.post(
                "/deployments",
                json={"application_id": app_id, "server_id": server_id},
                headers=headers,
            )
        return r.json()["data"]  # type: ignore[return-value]

    def test_filter_by_status_success(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, server_id, app_id, _ = self._setup(c)

        # Buat 1 deployment sukses
        self._deploy(c, headers, app_id, server_id)

        r = c.get("/deployments?status=success", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) >= 1
        assert all(d["status"] == "success" for d in data)

    def test_filter_by_status_failed_returns_empty_when_none(
        self, client: object
    ) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, server_id, app_id, _ = self._setup(c)

        # Buat deployment sukses saja
        self._deploy(c, headers, app_id, server_id)

        r = c.get("/deployments?status=failed", headers=headers)
        assert r.status_code == 200
        # User baru, tidak ada deployment failed
        assert all(d["status"] == "failed" for d in r.json()["data"])

    def test_filter_by_application_id_and_status(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, server_id, app_id, _ = self._setup(c)

        self._deploy(c, headers, app_id, server_id)

        r = c.get(
            f"/deployments?application_id={app_id}&status=success",
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert all(
            d["application_id"] == app_id and d["status"] == "success"
            for d in data
        )

    def test_pagination_limit(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, server_id, app_id, _ = self._setup(c)

        # Buat 3 deployment
        for _ in range(3):
            self._deploy(c, headers, app_id, server_id)

        r = c.get(
            f"/deployments?application_id={app_id}&limit=2", headers=headers
        )
        assert r.status_code == 200
        assert len(r.json()["data"]) == 2

    def test_pagination_offset(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, server_id, app_id, _ = self._setup(c)

        for _ in range(3):
            self._deploy(c, headers, app_id, server_id)

        r_all = c.get(
            f"/deployments?application_id={app_id}&limit=10&offset=0",
            headers=headers,
        )
        r_offset = c.get(
            f"/deployments?application_id={app_id}&limit=10&offset=1",
            headers=headers,
        )
        assert len(r_offset.json()["data"]) == len(r_all.json()["data"]) - 1

    def test_response_includes_duration_on_finished_deployment(
        self, client: object
    ) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, server_id, app_id, _ = self._setup(c)

        dep = self._deploy(c, headers, app_id, server_id)
        dep_id = dep["id"]

        r = c.get(f"/deployments/{dep_id}", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        # Deployment sukses harus punya finished_at dan duration >= 0
        assert data["finished_at"] is not None
        assert data["duration"] is not None
        assert data["duration"] >= 0.0

    def test_response_duration_none_for_in_progress_deployment(
        self, client: object
    ) -> None:
        """Duration harus None ketika finished_at belum diset (pending/deploying)."""
        from app.schemas.deployment import DeploymentResponse
        from datetime import timezone

        resp = DeploymentResponse(
            id=99,
            application_id=1,
            server_id=1,
            status=DeploymentStatus.deploying,
            branch="main",
            commit_sha=None,
            log_path=None,
            started_at=datetime.now(tz=timezone.utc),
            finished_at=None,
        )
        assert resp.duration is None

    def test_response_includes_commit_sha_after_success(
        self, client: object
    ) -> None:
        from fastapi.testclient import TestClient
        from app.services.health_check import HealthCheckResult
        c: TestClient = client  # type: ignore[assignment]
        headers, server_id, app_id, _ = self._setup(c)

        clone_result = _make_clone_result(sha="cafebabe12345678")
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
        ):
            r = c.post(
                "/deployments",
                json={"application_id": app_id, "server_id": server_id},
                headers=headers,
            )

        dep_id = r.json()["data"]["id"]
        detail = c.get(f"/deployments/{dep_id}", headers=headers)
        assert detail.json()["data"]["commit_sha"] == "cafebabe12345678"

    def test_invalid_status_filter_returns_422(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, _, _, _ = self._setup(c)

        r = c.get("/deployments?status=invalid_status", headers=headers)
        assert r.status_code == 422

    def test_negative_offset_returns_422(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, _, _, _ = self._setup(c)

        r = c.get("/deployments?offset=-1", headers=headers)
        assert r.status_code == 422

    def test_limit_exceeds_max_returns_422(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, _, _, _ = self._setup(c)

        r = c.get("/deployments?limit=9999", headers=headers)
        assert r.status_code == 422


# ==========================================================================
# Task 3.8 — Health Check Tests
# ==========================================================================

# ---------------------------------------------------------------------------
# _check_compose_containers — unit tests
# ---------------------------------------------------------------------------

class TestCheckComposeContainers:
    """Test fungsi _check_compose_containers dengan mock Docker client."""

    def _make_container(self, name: str, status: str, health: str = "") -> MagicMock:
        c = MagicMock()
        c.name = name
        c.status = status
        if health:
            c.attrs = {"State": {"Health": {"Status": health}}}
        else:
            c.attrs = {"State": {}}
        return c

    def test_all_running_returns_healthy(self) -> None:
        from app.services.health_check import _check_compose_containers  # type: ignore[attr-defined]

        containers = [
            self._make_container("web_1", "running"),
            self._make_container("db_1", "running"),
        ]
        mock_client = MagicMock()
        mock_client.containers.list.return_value = containers

        with patch("docker.from_env", return_value=mock_client):
            result = _check_compose_containers("myproject")

        assert result.healthy is True
        assert result.containers_checked == 2

    def test_exited_container_returns_unhealthy(self) -> None:
        from app.services.health_check import _check_compose_containers  # type: ignore[attr-defined]

        containers = [
            self._make_container("web_1", "running"),
            self._make_container("worker_1", "exited"),
        ]
        mock_client = MagicMock()
        mock_client.containers.list.return_value = containers

        with patch("docker.from_env", return_value=mock_client):
            result = _check_compose_containers("myproject")

        assert result.healthy is False
        assert result.statuses["worker_1"] == "exited"

    def test_restarting_container_returns_unhealthy(self) -> None:
        from app.services.health_check import _check_compose_containers  # type: ignore[attr-defined]

        containers = [self._make_container("app_1", "restarting")]
        mock_client = MagicMock()
        mock_client.containers.list.return_value = containers

        with patch("docker.from_env", return_value=mock_client):
            result = _check_compose_containers("myproject")

        assert result.healthy is False

    def test_no_containers_returns_unhealthy(self) -> None:
        from app.services.health_check import _check_compose_containers  # type: ignore[attr-defined]

        mock_client = MagicMock()
        mock_client.containers.list.return_value = []

        with patch("docker.from_env", return_value=mock_client):
            result = _check_compose_containers("myproject")

        assert result.healthy is False
        assert result.containers_checked == 0
        assert "Tidak ada container" in result.message

    def test_healthcheck_status_takes_priority_over_raw_status(self) -> None:
        from app.services.health_check import _check_compose_containers  # type: ignore[attr-defined]

        # Container raw status=running tapi healthcheck=unhealthy
        containers = [self._make_container("app_1", "running", health="unhealthy")]
        mock_client = MagicMock()
        mock_client.containers.list.return_value = containers

        with patch("docker.from_env", return_value=mock_client):
            result = _check_compose_containers("myproject")

        assert result.healthy is False
        assert result.statuses["app_1"] == "unhealthy"

    def test_healthy_healthcheck_status_returns_healthy(self) -> None:
        from app.services.health_check import _check_compose_containers  # type: ignore[attr-defined]

        containers = [self._make_container("app_1", "running", health="healthy")]
        mock_client = MagicMock()
        mock_client.containers.list.return_value = containers

        with patch("docker.from_env", return_value=mock_client):
            result = _check_compose_containers("myproject")

        assert result.healthy is True

    def test_uses_label_filter_for_compose_project(self) -> None:
        from app.services.health_check import _check_compose_containers  # type: ignore[attr-defined]

        mock_client = MagicMock()
        mock_client.containers.list.return_value = []

        with patch("docker.from_env", return_value=mock_client):
            _check_compose_containers("my-compose-project")

        call_kwargs = mock_client.containers.list.call_args.kwargs
        assert call_kwargs["filters"]["label"] == "com.docker.compose.project=my-compose-project"

    def test_docker_connection_error_raises_runtime_error(self) -> None:
        from app.services.health_check import _check_compose_containers  # type: ignore[attr-defined]

        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("connection refused")

        with patch("docker.from_env", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Tidak dapat terhubung"):
                _check_compose_containers("myproject")


# ---------------------------------------------------------------------------
# verify_deployment_health — async unit tests (asyncio.sleep di-mock)
# ---------------------------------------------------------------------------

class TestVerifyDeploymentHealth:
    """
    Test verify_deployment_health — dijalankan via asyncio.run() (sync),
    asyncio.sleep di-mock agar test instan tanpa menunggu.
    """

    def test_returns_healthy_when_containers_running(self) -> None:
        import asyncio
        from app.services.health_check import HealthCheckResult, verify_deployment_health

        healthy_result = HealthCheckResult(healthy=True, containers_checked=2, message="ok")

        async def _run() -> HealthCheckResult:
            with (
                patch("asyncio.sleep"),
                patch("app.services.health_check._check_compose_containers", return_value=healthy_result),
            ):
                return await verify_deployment_health("myproject", startup_delay=0)

        result = asyncio.run(_run())
        assert result.healthy is True
        assert result.containers_checked == 2

    def test_returns_unhealthy_when_container_exited(self) -> None:
        import asyncio
        from app.services.health_check import HealthCheckResult, verify_deployment_health

        unhealthy = HealthCheckResult(
            healthy=False, containers_checked=1,
            statuses={"app_1": "exited"}, message="app_1 exited",
        )

        async def _run() -> HealthCheckResult:
            with (
                patch("asyncio.sleep"),
                patch("app.services.health_check._check_compose_containers", return_value=unhealthy),
            ):
                return await verify_deployment_health("myproject", startup_delay=0, retries=1)

        result = asyncio.run(_run())
        assert result.healthy is False
        assert result.statuses["app_1"] == "exited"

    def test_retries_on_unhealthy_then_succeeds(self) -> None:
        import asyncio
        from app.services.health_check import HealthCheckResult, verify_deployment_health

        call_count = 0

        def side_effect(project: str) -> HealthCheckResult:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return HealthCheckResult(healthy=False, containers_checked=1, message="not ready")
            return HealthCheckResult(healthy=True, containers_checked=1, message="ok")

        async def _run() -> HealthCheckResult:
            with (
                patch("asyncio.sleep"),
                patch("app.services.health_check._check_compose_containers", side_effect=side_effect),
            ):
                return await verify_deployment_health("myproject", startup_delay=0, retries=3)

        result = asyncio.run(_run())
        assert result.healthy is True
        assert call_count == 3

    def test_startup_delay_passed_to_sleep(self) -> None:
        import asyncio
        from app.services.health_check import HealthCheckResult, verify_deployment_health

        healthy = HealthCheckResult(healthy=True, containers_checked=1, message="ok")
        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        async def _run() -> HealthCheckResult:
            with (
                patch("asyncio.sleep", side_effect=fake_sleep),
                patch("app.services.health_check._check_compose_containers", return_value=healthy),
            ):
                return await verify_deployment_health("proj", startup_delay=5.0, retries=1)

        asyncio.run(_run())
        assert sleep_calls[0] == 5.0

    def test_zero_startup_delay_calls_sleep_with_zero(self) -> None:
        import asyncio
        from app.services.health_check import HealthCheckResult, verify_deployment_health

        healthy = HealthCheckResult(healthy=True, containers_checked=1, message="ok")
        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        async def _run() -> HealthCheckResult:
            with (
                patch("asyncio.sleep", side_effect=fake_sleep),
                patch("app.services.health_check._check_compose_containers", return_value=healthy),
            ):
                return await verify_deployment_health("proj", startup_delay=0.0, retries=1)

        asyncio.run(_run())
        assert sleep_calls[0] == 0.0


# ---------------------------------------------------------------------------
# run_health_check — sync wrapper tests
# ---------------------------------------------------------------------------

class TestRunHealthCheck:
    def test_returns_health_check_result(self) -> None:
        from app.services.health_check import HealthCheckResult, run_health_check

        expected = HealthCheckResult(healthy=True, containers_checked=1, message="ok")

        with patch(
            "app.services.health_check.verify_deployment_health",
            return_value=expected,
        ):
            # Mock asyncio.run untuk menghindari nested event loop
            with patch("asyncio.run", return_value=expected):
                result = run_health_check("myproject", startup_delay=0)

        assert result.healthy is True

    def test_calls_asyncio_run(self) -> None:
        from app.services.health_check import HealthCheckResult, run_health_check

        expected = HealthCheckResult(healthy=False, containers_checked=0, message="err")

        with patch("asyncio.run", return_value=expected) as mock_run:
            run_health_check("proj", startup_delay=0, retries=1)

        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# _run_deployment integration dengan health check
# ---------------------------------------------------------------------------

class TestRunDeploymentWithHealthCheck:
    """Test integrasi _run_deployment + health check — semua dep di-mock."""

    _patches: dict[str, str] = {
        "clone": "app.services.deployment_service.git_service.clone_repository",
        "cleanup": "app.services.deployment_service.git_service.cleanup",
        "run_compose": "app.services.deployment_service._run_compose",
        "write_env": "app.services.deployment_service._write_env_file",
        "update_status": "app.services.deployment_service.deployment_repository.update_status",
        "list_env": "app.services.deployment_service.env_var_repository.list_by_project",
        "health_check": "app.services.deployment_service.health_check_service.run_health_check",
    }

    def _healthy(self) -> MagicMock:
        from app.services.health_check import HealthCheckResult
        r = MagicMock(spec=HealthCheckResult)
        r.healthy = True
        r.containers_checked = 2
        r.message = "All healthy"
        return r

    def _unhealthy(self, status_val: str = "exited") -> MagicMock:
        from app.services.health_check import HealthCheckResult
        r = MagicMock(spec=HealthCheckResult)
        r.healthy = False
        r.containers_checked = 1
        r.statuses = {"app_1": status_val}
        r.message = f"app_1 is {status_val}"
        return r

    def test_healthy_result_sets_status_success(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()

        with (
            patch(self._patches["clone"], return_value=_make_clone_result()),
            patch(self._patches["cleanup"]),
            patch(self._patches["run_compose"], return_value=("ok", "")),
            patch(self._patches["write_env"]),
            patch(self._patches["list_env"], return_value=[]),
            patch(self._patches["health_check"], return_value=self._healthy()),
            patch(self._patches["update_status"]) as mock_update,
        ):
            _run_deployment(db, deployment, app, server)

        statuses = [c.args[2] for c in mock_update.call_args_list]
        assert DeploymentStatus.success in statuses
        assert DeploymentStatus.failed not in statuses

    def test_exited_container_sets_status_failed(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()

        with (
            patch(self._patches["clone"], return_value=_make_clone_result()),
            patch(self._patches["cleanup"]),
            patch(self._patches["run_compose"], return_value=("ok", "")),
            patch(self._patches["write_env"]),
            patch(self._patches["list_env"], return_value=[]),
            patch(self._patches["health_check"], return_value=self._unhealthy("exited")),
            patch(self._patches["update_status"]) as mock_update,
        ):
            with pytest.raises(RuntimeError, match="Health check gagal"):
                _run_deployment(db, deployment, app, server)

        statuses = [c.args[2] for c in mock_update.call_args_list]
        assert DeploymentStatus.failed in statuses
        assert DeploymentStatus.success not in statuses

    def test_restarting_container_sets_status_failed(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()

        with (
            patch(self._patches["clone"], return_value=_make_clone_result()),
            patch(self._patches["cleanup"]),
            patch(self._patches["run_compose"], return_value=("ok", "")),
            patch(self._patches["write_env"]),
            patch(self._patches["list_env"], return_value=[]),
            patch(self._patches["health_check"], return_value=self._unhealthy("restarting")),
            patch(self._patches["update_status"]) as mock_update,
        ):
            with pytest.raises(RuntimeError):
                _run_deployment(db, deployment, app, server)

        statuses = [c.args[2] for c in mock_update.call_args_list]
        assert DeploymentStatus.failed in statuses

    def test_no_containers_found_sets_status_failed(self) -> None:
        from app.services.health_check import HealthCheckResult
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()

        no_container = HealthCheckResult(
            healthy=False,
            containers_checked=0,
            message="Tidak ada container ditemukan",
        )

        with (
            patch(self._patches["clone"], return_value=_make_clone_result()),
            patch(self._patches["cleanup"]),
            patch(self._patches["run_compose"], return_value=("ok", "")),
            patch(self._patches["write_env"]),
            patch(self._patches["list_env"], return_value=[]),
            patch(self._patches["health_check"], return_value=no_container),
            patch(self._patches["update_status"]) as mock_update,
        ):
            with pytest.raises(RuntimeError):
                _run_deployment(db, deployment, app, server)

        statuses = [c.args[2] for c in mock_update.call_args_list]
        assert DeploymentStatus.failed in statuses

    def test_health_check_called_with_compose_project(self) -> None:
        from app.services.deployment_service import _run_deployment  # type: ignore[attr-defined]

        db = MagicMock()
        app = _make_app()
        server = _make_server()
        deployment = _make_deployment()
        clone_result = _make_clone_result()

        with (
            patch(self._patches["clone"], return_value=clone_result),
            patch(self._patches["cleanup"]),
            patch(self._patches["run_compose"], return_value=("ok", "")),
            patch(self._patches["write_env"]),
            patch(self._patches["list_env"], return_value=[]),
            patch(self._patches["health_check"], return_value=self._healthy()) as mock_hc,
            patch(self._patches["update_status"]),
        ):
            _run_deployment(db, deployment, app, server)

        # compose_project harus = nama direktori clone
        call_kwargs = mock_hc.call_args.kwargs
        assert call_kwargs["compose_project"] == clone_result.repo_dir.name


# ---------------------------------------------------------------------------
# Manual health-check endpoint tests
# ---------------------------------------------------------------------------

class TestManualHealthCheckEndpoint:
    def _setup(self, client: object) -> tuple[dict[str, str], int]:
        """Buat user + deployment sukses, return (headers, deployment_id)."""
        import uuid
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]

        suffix = uuid.uuid4().hex[:8]
        user = {"username": f"hc_{suffix}", "email": f"hc_{suffix}@x.com", "password": "pass1234"}
        c.post("/auth/register", json=user)
        r = c.post("/auth/login", data={"username": user["username"], "password": user["password"]})
        headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

        proj_id = c.post("/projects", json={"name": f"p{suffix}", "description": "t"}, headers=headers).json()["data"]["id"]
        srv_id = c.post("/servers", json={"name": "s", "host": "1.2.3.4", "port": 22, "username": "u", "auth_type": "password", "password": "x"}, headers=headers).json()["data"]["id"]
        app_id = c.post("/applications", json={"project_id": proj_id, "name": "a", "repository": "https://github.com/org/repo.git", "branch": "main"}, headers=headers).json()["data"]["id"]

        from app.services.health_check import HealthCheckResult
        healthy = HealthCheckResult(healthy=True, containers_checked=1, message="ok")

        with (
            patch("app.services.deployment_service.git_service.clone_repository", return_value=_make_clone_result()),
            patch("app.services.deployment_service.git_service.cleanup"),
            patch("app.services.deployment_service._run_compose", return_value=("ok", "")),
            patch("app.services.deployment_service.health_check_service.run_health_check", return_value=healthy),
        ):
            dep_r = c.post("/deployments", json={"application_id": app_id, "server_id": srv_id}, headers=headers)

        dep_id = dep_r.json()["data"]["id"]
        return headers, dep_id

    def test_manual_health_check_running_returns_200_healthy(self, client: object) -> None:
        from fastapi.testclient import TestClient
        from app.services.health_check import HealthCheckResult
        c: TestClient = client  # type: ignore[assignment]
        headers, dep_id = self._setup(c)

        healthy = HealthCheckResult(
            healthy=True,
            containers_checked=2,
            statuses={"web_1": "running", "db_1": "running"},
            message="All healthy",
        )
        with patch("app.services.health_check.run_health_check", return_value=healthy):
            r = c.post(f"/deployments/{dep_id}/health-check", headers=headers)

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["healthy"] is True
        assert data["containers_checked"] == 2
        assert data["statuses"]["web_1"] == "running"

    def test_manual_health_check_exited_returns_200_unhealthy(self, client: object) -> None:
        from fastapi.testclient import TestClient
        from app.services.health_check import HealthCheckResult
        c: TestClient = client  # type: ignore[assignment]
        headers, dep_id = self._setup(c)

        unhealthy = HealthCheckResult(
            healthy=False,
            containers_checked=1,
            statuses={"app_1": "exited"},
            message="app_1 exited",
        )
        with patch("app.services.health_check.run_health_check", return_value=unhealthy):
            r = c.post(f"/deployments/{dep_id}/health-check", headers=headers)

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["healthy"] is False
        assert data["statuses"]["app_1"] == "exited"

    def test_manual_health_check_not_found_returns_404(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, _ = self._setup(c)
        r = c.post("/deployments/99999/health-check", headers=headers)
        assert r.status_code == 404

    def test_manual_health_check_without_auth_returns_401(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.post("/deployments/1/health-check")
        assert r.status_code == 401

    def test_manual_health_check_other_user_returns_404(self, client: object) -> None:
        """User lain tidak boleh akses health-check milik user pertama."""
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        _, dep_id = self._setup(c)

        # Login sebagai user baru
        import uuid
        suffix = uuid.uuid4().hex[:8]
        user_b = {"username": f"hcb_{suffix}", "email": f"hcb_{suffix}@x.com", "password": "pass1234"}
        c.post("/auth/register", json=user_b)
        r = c.post("/auth/login", data={"username": user_b["username"], "password": user_b["password"]})
        headers_b = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

        r2 = c.post(f"/deployments/{dep_id}/health-check", headers=headers_b)
        assert r2.status_code == 404

    def test_manual_health_check_docker_error_returns_503(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers, dep_id = self._setup(c)

        with patch(
            "app.services.health_check.run_health_check",
            side_effect=RuntimeError("Docker daemon not reachable"),
        ):
            r = c.post(f"/deployments/{dep_id}/health-check", headers=headers)

        assert r.status_code == 503
