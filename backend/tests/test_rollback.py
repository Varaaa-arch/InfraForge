"""
Tests untuk fitur Manual Rollback (P0 Item #2).

Coverage:
  - get_last_successful: query deployment sukses terakhir
  - deployment_repository.create: rollback columns tersimpan
  - rollback_deployment service: happy path, guard conditions
  - POST /deployments/{id}/rollback endpoint (async):
      - happy path → 202 + background task dijadwalkan
      - target bukan success → 422
      - target tidak ditemukan → 404
      - target milik app lain → 404
      - aplikasi sedang deploying (locked) → 409
      - server target sudah dihapus → 422
  - DeploymentResponse schema: field is_rollback, rollback_of, compose_path_snapshot
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.deployment import Deployment, DeploymentStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_login(client) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    user = {"username": f"rb_{suffix}", "email": f"rb_{suffix}@t.com", "password": "pass1234"}
    client.post("/auth/register", json=user)
    r = client.post("/auth/login", data={"username": user["username"], "password": user["password"]})
    token = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project(client, headers) -> int:
    r = client.post("/projects", json={"name": f"p-{uuid.uuid4().hex[:6]}", "description": "t"}, headers=headers)
    return int(r.json()["data"]["id"])


def _create_server(client, headers) -> int:
    r = client.post("/servers", json={
        "name": "srv", "host": "10.0.0.1", "port": 22,
        "username": "ubuntu", "auth_type": "password", "password": "s"
    }, headers=headers)
    return int(r.json()["data"]["id"])


def _create_app(client, headers, project_id) -> int:
    r = client.post("/applications", json={
        "project_id": project_id, "name": f"app-{uuid.uuid4().hex[:6]}",
        "repository": "https://github.com/org/repo", "branch": "main",
    }, headers=headers)
    return int(r.json()["data"]["id"])


def _make_deployment(
    db,
    app_id: int,
    server_id: int | None,
    status: str,
    compose_path: str = "docker-compose.yml",
    *,
    tag: str | None = None,
    commit_sha: str | None = None,
    triggered_by: str | None = None,
) -> Deployment:
    """Buat deployment record langsung di DB untuk testing."""
    from app.repositories import deployment_repository
    from app.models.deployment import DeploymentStatus as DS

    dep = deployment_repository.create(
        db,
        app_id,
        server_id,
        "main",
        tag=tag,
        commit_sha=commit_sha,
        triggered_by=triggered_by,
    )
    # Update status langsung
    if status == "success":
        deployment_repository.update_status(
            db, dep, DS.success,
            compose_path_snapshot=compose_path,
        )
    elif status == "failed":
        deployment_repository.update_status(db, dep, DS.failed)
    elif status == "deploying":
        deployment_repository.update_status(db, dep, DS.deploying)
    db.refresh(dep)
    return dep


# ---------------------------------------------------------------------------
# Unit tests: deployment_repository.get_last_successful
# ---------------------------------------------------------------------------

class TestGetLastSuccessful:
    def _make_app_and_server(self, client, headers) -> tuple[int, int]:
        pid = _create_project(client, headers)
        sid = _create_server(client, headers)
        aid = _create_app(client, headers, pid)
        return aid, sid

    def test_returns_latest_success(self, client, db_session) -> None:
        from app.repositories import deployment_repository
        from app.models.deployment import DeploymentStatus as DS

        headers = _register_and_login(client)
        app_id, server_id = self._make_app_and_server(client, headers)

        d1 = deployment_repository.create(db_session, app_id, server_id, "main")
        deployment_repository.update_status(db_session, d1, DS.success)
        d2 = deployment_repository.create(db_session, app_id, server_id, "main")
        deployment_repository.update_status(db_session, d2, DS.success)

        result = deployment_repository.get_last_successful(db_session, app_id)
        assert result is not None
        assert result.id == d2.id  # yang terbaru

    def test_returns_none_when_no_success(self, client, db_session) -> None:
        from app.repositories import deployment_repository
        from app.models.deployment import DeploymentStatus as DS

        headers = _register_and_login(client)
        app_id, server_id = self._make_app_and_server(client, headers)

        d = deployment_repository.create(db_session, app_id, server_id, "main")
        deployment_repository.update_status(db_session, d, DS.failed)

        result = deployment_repository.get_last_successful(db_session, app_id)
        assert result is None

    def test_exclude_id(self, client, db_session) -> None:
        from app.repositories import deployment_repository
        from app.models.deployment import DeploymentStatus as DS

        headers = _register_and_login(client)
        app_id, server_id = self._make_app_and_server(client, headers)

        d1 = deployment_repository.create(db_session, app_id, server_id, "main")
        deployment_repository.update_status(db_session, d1, DS.success)
        d2 = deployment_repository.create(db_session, app_id, server_id, "main")
        deployment_repository.update_status(db_session, d2, DS.success)

        # Exclude d2 → harus dapat d1
        result = deployment_repository.get_last_successful(db_session, app_id, exclude_id=d2.id)
        assert result is not None
        assert result.id == d1.id


# ---------------------------------------------------------------------------
# Unit tests: deployment_repository.create rollback columns
# ---------------------------------------------------------------------------

class TestDeploymentRepositoryCreateRollback:
    def test_create_with_rollback_fields(self, client, db_session) -> None:
        from app.repositories import deployment_repository

        headers = _register_and_login(client)
        pid = _create_project(client, headers)
        sid = _create_server(client, headers)
        app_id = _create_app(client, headers, pid)

        target = deployment_repository.create(db_session, app_id, sid, "main")
        rb = deployment_repository.create(
            db_session, app_id, sid, "main",
            rollback_of=target.id,
            compose_path_snapshot="docker-compose.prod.yml",
            is_rollback=True,
        )

        assert rb.rollback_of == target.id
        assert rb.compose_path_snapshot == "docker-compose.prod.yml"
        assert rb.is_rollback is True

    def test_create_normal_deployment_has_rollback_defaults(self, client, db_session) -> None:
        from app.repositories import deployment_repository

        headers = _register_and_login(client)
        pid = _create_project(client, headers)
        sid = _create_server(client, headers)
        app_id = _create_app(client, headers, pid)

        dep = deployment_repository.create(db_session, app_id, sid, "main")
        assert dep.rollback_of is None
        assert dep.compose_path_snapshot is None
        assert dep.is_rollback is False


# ---------------------------------------------------------------------------
# Unit tests: DeploymentResponse schema rollback fields
# ---------------------------------------------------------------------------

class TestDeploymentResponseRollbackFields:
    def _make_mock_dep(self, **kwargs) -> MagicMock:
        dep = MagicMock(spec=Deployment)
        dep.id = 1
        dep.application_id = 1
        dep.server_id = 1
        dep.status = DeploymentStatus.success
        dep.branch = "main"
        dep.commit_sha = "abc123"
        dep.log_path = None
        dep.started_at = datetime.now(tz=timezone.utc)
        dep.finished_at = datetime.now(tz=timezone.utc)
        dep.is_rollback = False
        dep.rollback_of = None
        dep.compose_path_snapshot = None
        dep.trigger_source = "manual"
        dep.tag = None
        dep.triggered_by = None
        for k, v in kwargs.items():
            setattr(dep, k, v)
        return dep

    def test_normal_deployment_rollback_fields_default(self) -> None:
        from app.schemas.deployment import DeploymentResponse

        dep = self._make_mock_dep()
        resp = DeploymentResponse.model_validate(dep)
        assert resp.is_rollback is False
        assert resp.rollback_of is None
        assert resp.compose_path_snapshot is None

    def test_rollback_deployment_fields_populated(self) -> None:
        from app.schemas.deployment import DeploymentResponse

        dep = self._make_mock_dep(
            is_rollback=True,
            rollback_of=42,
            compose_path_snapshot="docker-compose.prod.yml",
        )
        resp = DeploymentResponse.model_validate(dep)
        assert resp.is_rollback is True
        assert resp.rollback_of == 42
        assert resp.compose_path_snapshot == "docker-compose.prod.yml"


# ---------------------------------------------------------------------------
# Integration tests: POST /deployments/{id}/rollback (async, 202)
# ---------------------------------------------------------------------------

class TestRollbackEndpoint:
    def _setup(self, client) -> tuple[dict[str, str], int, int, int]:
        headers = _register_and_login(client)
        project_id = _create_project(client, headers)
        server_id = _create_server(client, headers)
        app_id = _create_app(client, headers, project_id)
        return headers, project_id, server_id, app_id

    def test_rollback_target_not_found_returns_404(self, client) -> None:
        headers = _register_and_login(client)
        r = client.post("/deployments/99999/rollback", headers=headers)
        assert r.status_code == 404

    def test_rollback_target_owned_by_other_user_returns_404(
        self, client, db_session
    ) -> None:
        _headers1, _pid, server_id, app_id = self._setup(client)
        target = _make_deployment(db_session, app_id, server_id, "success")

        headers2 = _register_and_login(client)
        r = client.post(f"/deployments/{target.id}/rollback", headers=headers2)
        assert r.status_code == 404

    def test_rollback_non_success_deployment_returns_422(
        self, client, db_session
    ) -> None:
        headers, _pid, server_id, app_id = self._setup(client)
        target = _make_deployment(db_session, app_id, server_id, "failed")

        r = client.post(f"/deployments/{target.id}/rollback", headers=headers)
        assert r.status_code == 422
        assert "success" in r.json()["message"].lower()

    def test_rollback_locked_app_returns_409(self, client, db_session) -> None:
        headers, _pid, server_id, app_id = self._setup(client)
        target = _make_deployment(db_session, app_id, server_id, "success")

        with (
            patch(
                "app.services.deployment_queue.is_deployment_running",
                return_value=True,
            ),
            patch(
                "app.services.deployment_queue.get_running_deployment_id",
                return_value=99,
            ),
        ):
            r = client.post(f"/deployments/{target.id}/rollback", headers=headers)

        assert r.status_code == 409
        assert "sedang dalam proses deployment" in r.json()["message"]

    def test_rollback_server_deleted_returns_422(
        self, client, db_session
    ) -> None:
        headers, _pid, _server_id, app_id = self._setup(client)
        target = _make_deployment(db_session, app_id, None, "success")

        r = client.post(f"/deployments/{target.id}/rollback", headers=headers)
        assert r.status_code == 422
        assert "server" in r.json()["message"].lower()

    def test_rollback_happy_path_returns_202_and_schedules(
        self, client, db_session
    ) -> None:
        headers, _pid, server_id, app_id = self._setup(client)
        target = _make_deployment(
            db_session,
            app_id,
            server_id,
            "success",
            compose_path="deploy/prod-compose.yml",
            tag="v1.4.2",
            commit_sha="a" * 40,
            triggered_by="ci",
        )

        with patch(
            "app.services.deployment_queue.run_deployment_background"
        ) as background_mock:
            r = client.post(
                f"/deployments/{target.id}/rollback", headers=headers
            )

        assert r.status_code == 202
        data = r.json()["data"]
        assert data["status"] == "pending"
        assert data["is_rollback"] is True
        assert data["rollback_of"] == target.id
        assert data["tag"] == "v1.4.2"
        assert data["commit_sha"] == "a" * 40
        assert data["compose_path_snapshot"] == "deploy/prod-compose.yml"
        assert data["triggered_by"].startswith("rb_")
        assert data["finished_at"] is None

        background_mock.assert_called_once_with(
            deployment_id=data["id"],
            application_id=app_id,
            server_id=server_id,
        )

    def test_rollback_preserves_exact_target_version_in_db(
        self, client, db_session
    ) -> None:
        headers, _pid, server_id, app_id = self._setup(client)
        target = _make_deployment(
            db_session,
            app_id,
            server_id,
            "success",
            tag="release-9",
            commit_sha="b" * 40,
        )

        with patch("app.services.deployment_queue.run_deployment_background"):
            r = client.post(
                f"/deployments/{target.id}/rollback", headers=headers
            )

        assert r.status_code == 202
        from app.repositories import deployment_repository

        rollback = deployment_repository.get_by_id(
            db_session, int(r.json()["data"]["id"])
        )
        assert rollback is not None
        assert rollback.is_rollback is True
        assert rollback.rollback_of == target.id
        assert rollback.branch == target.branch
        assert rollback.tag == "release-9"
        assert rollback.commit_sha == "b" * 40
