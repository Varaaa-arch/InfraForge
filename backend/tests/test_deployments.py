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
        }

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
            patch(p["update_status"]) as mock_update,
        ):
            _run_deployment(db, deployment, app, server)

        # Harus ada panggilan update_status dengan DeploymentStatus.success
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
                return_value=("ok", ""),
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
                return_value=("ok", ""),
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
                return_value=("ok", ""),
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
                return_value=("ok", ""),
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
        c: TestClient = client  # type: ignore[assignment]

        # User A buat deployment
        headers_a = self._register_and_login(c)
        project_id = self._create_project(c, headers_a)
        server_id = self._create_server(c, headers_a)
        app_id = self._create_app(c, headers_a, project_id)

        clone_result = _make_clone_result()
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
