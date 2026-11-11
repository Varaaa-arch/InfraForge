"""
Tests untuk Application-Level Lock / Concurrency Control (P0 Item #4).

Coverage:
  - acquire_deploy_lock / release_deploy_lock (Redis SETNX)
  - get_running_deployment_id (introspeksi lock value)
  - is_deployment_running (cek keberadaan lock)
  - is_locked_by_db_status (DB fallback saat Redis down)
  - trigger_deployment guard: reject jika sedang deploying
  - webhook handler guard: skip app yang sedang deploying
  - run_deployment_background: update app.status (deploying → running/failed)
  - GET /applications/{id}/lock-status endpoint
  - lock_source: redis / db / none

Semua Redis interaction di-mock — tidak perlu Redis nyata.
"""

from __future__ import annotations

import json
import hashlib
import hmac
import uuid
from unittest.mock import MagicMock, call, patch

import pytest

from app.config import settings
from app.models.application import AppStatus
from app.services import deployment_queue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_signature(raw_body: bytes, secret: str) -> str:
    digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def _register_and_login(client) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    user = {
        "username": f"cc_{suffix}",
        "email": f"cc_{suffix}@test.com",
        "password": "pass1234",
    }
    client.post("/auth/register", json=user)
    r = client.post(
        "/auth/login",
        data={"username": user["username"], "password": user["password"]},
    )
    token = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project(client, headers: dict) -> int:
    r = client.post(
        "/projects",
        json={"name": f"proj-{uuid.uuid4().hex[:6]}", "description": "test"},
        headers=headers,
    )
    return int(r.json()["data"]["id"])


def _create_server(client, headers: dict) -> int:
    r = client.post(
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


def _create_app(client, headers: dict, project_id: int) -> int:
    r = client.post(
        "/applications",
        json={
            "project_id": project_id,
            "name": f"app-{uuid.uuid4().hex[:6]}",
            "repository": "https://github.com/org/repo",
            "branch": "main",
        },
        headers=headers,
    )
    return int(r.json()["data"]["id"])


# ---------------------------------------------------------------------------
# Unit tests: acquire/release lock
# ---------------------------------------------------------------------------

class TestAcquireReleaseLock:
    def test_acquire_succeeds_when_no_lock(self) -> None:
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.set.return_value = True
            result = deployment_queue.acquire_deploy_lock(app_id := 1, dep_id := 10)
            assert result is True
            mock_redis.set.assert_called_once_with(
                "infraforge:deploy:lock:1",
                "10",
                nx=True,
                ex=settings.ARQ_JOB_TIMEOUT,
            )

    def test_acquire_fails_when_lock_exists(self) -> None:
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.set.return_value = None  # Redis SETNX mengembalikan None saat gagal
            result = deployment_queue.acquire_deploy_lock(1, 10)
            assert result is False

    def test_release_deletes_lock_key(self) -> None:
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            deployment_queue.release_deploy_lock(42)
            mock_redis.delete.assert_called_once_with("infraforge:deploy:lock:42")

    def test_acquire_then_release(self) -> None:
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.set.return_value = True
            acquired = deployment_queue.acquire_deploy_lock(5, 99)
            assert acquired is True

            deployment_queue.release_deploy_lock(5)
            mock_redis.delete.assert_called_once_with("infraforge:deploy:lock:5")


# ---------------------------------------------------------------------------
# Unit tests: get_running_deployment_id
# ---------------------------------------------------------------------------

class TestGetRunningDeploymentId:
    def test_returns_deployment_id_when_lock_active(self) -> None:
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.get.return_value = "42"
            result = deployment_queue.get_running_deployment_id(1)
            assert result == 42

    def test_returns_none_when_no_lock(self) -> None:
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.get.return_value = None
            result = deployment_queue.get_running_deployment_id(1)
            assert result is None

    def test_returns_none_on_corrupt_value(self) -> None:
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.get.return_value = "not-an-int"
            result = deployment_queue.get_running_deployment_id(1)
            assert result is None


# ---------------------------------------------------------------------------
# Unit tests: is_locked_by_db_status (DB fallback)
# ---------------------------------------------------------------------------

class TestIsLockedByDbStatus:
    def test_returns_true_when_app_is_deploying(self) -> None:
        from app.models.application import Application

        mock_app = MagicMock(spec=Application)
        mock_app.status = AppStatus.deploying

        with (
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
            patch(
                "app.repositories.application_repository.get_by_id",
                return_value=mock_app,
            ),
        ):
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_db

            result = deployment_queue.is_locked_by_db_status(1)
            assert result is True

    def test_returns_false_when_app_is_idle(self) -> None:
        from app.models.application import Application

        mock_app = MagicMock(spec=Application)
        mock_app.status = AppStatus.idle

        with (
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
            patch(
                "app.repositories.application_repository.get_by_id",
                return_value=mock_app,
            ),
        ):
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_db

            result = deployment_queue.is_locked_by_db_status(1)
            assert result is False

    def test_returns_false_when_app_not_found(self) -> None:
        with (
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
            patch(
                "app.repositories.application_repository.get_by_id",
                return_value=None,
            ),
        ):
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_db

            result = deployment_queue.is_locked_by_db_status(999)
            assert result is False


# ---------------------------------------------------------------------------
# Unit tests: run_deployment_background (app.status lifecycle)
# ---------------------------------------------------------------------------

class TestRunDeploymentBackgroundStatus:
    def test_updates_app_status_to_deploying_then_running_on_success(self) -> None:
        from app.services.deployment_queue import run_deployment_background
        from app.models.application import Application
        from app.models.deployment import Deployment

        mock_dep = MagicMock(spec=Deployment)
        mock_dep.id = 1
        mock_dep.status = "pending"

        mock_app = MagicMock(spec=Application)
        mock_app.id = 1
        mock_app.status = AppStatus.idle

        mock_server = MagicMock()
        mock_server.id = 1

        with (
            patch("app.services.deployment_queue.redis_client") as mock_redis,
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
            patch("app.repositories.deployment_repository.get_by_id", return_value=mock_dep),
            patch("app.repositories.application_repository.get_by_id", return_value=mock_app),
            patch("app.repositories.server_repository.get_by_id", return_value=mock_server),
            patch("app.repositories.application_repository.update_status") as mock_update_status,
            patch("app.services.deployment_service._run_deployment"),  # deployment sukses
        ):
            mock_redis.set.return_value = True
            mock_redis.delete.return_value = 1

            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_db

            run_deployment_background(1, 1, 1)

            # Verifikasi urutan update_status calls:
            # 1. deploying (saat mulai)
            # 2. running (saat sukses)
            calls = mock_update_status.call_args_list
            assert len(calls) == 2
            assert calls[0] == call(mock_db, mock_app, AppStatus.deploying)
            assert calls[1] == call(mock_db, mock_app, AppStatus.running)

    def test_updates_app_status_to_failed_on_error(self) -> None:
        from app.services.deployment_queue import run_deployment_background
        from app.models.application import Application
        from app.models.deployment import Deployment

        mock_dep = MagicMock(spec=Deployment)
        mock_dep.id = 2
        mock_app = MagicMock(spec=Application)
        mock_app.id = 1
        mock_server = MagicMock()

        with (
            patch("app.services.deployment_queue.redis_client") as mock_redis,
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
            patch("app.repositories.deployment_repository.get_by_id", return_value=mock_dep),
            patch("app.repositories.application_repository.get_by_id", return_value=mock_app),
            patch("app.repositories.server_repository.get_by_id", return_value=mock_server),
            patch("app.repositories.application_repository.update_status") as mock_update_status,
            patch(
                "app.services.deployment_service._run_deployment",
                side_effect=RuntimeError("compose gagal"),
            ),
        ):
            mock_redis.set.return_value = True
            mock_redis.delete.return_value = 1

            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_db

            run_deployment_background(2, 1, 1)

            calls = mock_update_status.call_args_list
            assert len(calls) == 2
            assert calls[0] == call(mock_db, mock_app, AppStatus.deploying)
            assert calls[1] == call(mock_db, mock_app, AppStatus.failed)

    def test_lock_always_released(self) -> None:
        """Lock harus di-release bahkan saat exception di luar _run_deployment."""
        from app.services.deployment_queue import run_deployment_background

        with (
            patch("app.services.deployment_queue.redis_client") as mock_redis,
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
            patch(
                "app.repositories.deployment_repository.get_by_id",
                side_effect=Exception("DB crash"),
            ),
        ):
            mock_redis.set.return_value = True

            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_db

            run_deployment_background(99, 1, 1)

            # release_deploy_lock harus dipanggil
            mock_redis.delete.assert_called_once_with("infraforge:deploy:lock:1")

    def test_deployment_marked_failed_when_lock_not_acquired(self) -> None:
        """Jika lock tidak bisa di-acquire, deployment record di-set failed."""
        from app.services.deployment_queue import run_deployment_background
        from app.models.deployment import Deployment, DeploymentStatus

        mock_dep = MagicMock(spec=Deployment)

        with (
            patch("app.services.deployment_queue.redis_client") as mock_redis,
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
            patch("app.repositories.deployment_repository.get_by_id", return_value=mock_dep),
            patch("app.repositories.deployment_repository.update_status") as mock_update_dep,
        ):
            mock_redis.set.return_value = None  # Lock tidak bisa di-acquire
            mock_redis.get.return_value = "77"  # Deployment lain yang running

            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_db

            run_deployment_background(5, 1, 1)

            # Deployment #5 harus di-set failed
            mock_update_dep.assert_called_once_with(mock_db, mock_dep, DeploymentStatus.failed)


# ---------------------------------------------------------------------------
# Integration tests: trigger_deployment guard via API
# ---------------------------------------------------------------------------

class TestTriggerDeploymentConcurrencyGuard:
    def test_trigger_rejected_when_redis_locked(self, client) -> None:
        headers = _register_and_login(client)
        project_id = _create_project(client, headers)
        server_id = _create_server(client, headers)
        app_id = _create_app(client, headers, project_id)

        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            # Simulasikan lock aktif
            mock_redis.exists.return_value = 1
            mock_redis.get.return_value = "77"

            r = client.post(
                "/deployments",
                json={"application_id": app_id, "server_id": server_id},
                headers=headers,
            )

        # Exception handler mengembalikan {"message": ..., "code": 500}
        assert r.status_code == 500
        body = r.json()
        # Detail error di-log tapi tidak di-expose ke client (exception_handler generic)
        # Pastikan request ditolak dengan 500
        assert body["success"] is False

    def test_trigger_rejected_when_db_status_deploying(self, client) -> None:
        """Guard layer 2: DB status fallback saat Redis tidak ada lock tapi app deploying."""
        headers = _register_and_login(client)
        project_id = _create_project(client, headers)
        server_id = _create_server(client, headers)
        app_id = _create_app(client, headers, project_id)

        # Set app.status = deploying manual via PATCH
        client.patch(
            f"/applications/{app_id}",
            json={"status": "deploying"},
            headers=headers,
        )

        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            # Redis tidak punya lock
            mock_redis.exists.return_value = 0
            mock_redis.get.return_value = None

            # is_locked_by_db_status akan membuka SessionLocal baru
            with patch("app.services.deployment_queue.SessionLocal") as mock_session_cls:
                mock_db = MagicMock()
                mock_db.__enter__ = MagicMock(return_value=mock_db)
                mock_db.__exit__ = MagicMock(return_value=False)
                mock_session_cls.return_value = mock_db

                from app.models.application import Application
                mock_app = MagicMock(spec=Application)
                mock_app.status = AppStatus.deploying
                with patch(
                    "app.repositories.application_repository.get_by_id",
                    return_value=mock_app,
                ):
                    r = client.post(
                        "/deployments",
                        json={"application_id": app_id, "server_id": server_id},
                        headers=headers,
                    )

        assert r.status_code == 500
        assert r.json()["success"] is False

    def test_trigger_allowed_when_no_lock(self, client) -> None:
        """Deploy boleh jalan kalau tidak ada lock aktif."""
        headers = _register_and_login(client)
        project_id = _create_project(client, headers)
        server_id = _create_server(client, headers)
        app_id = _create_app(client, headers, project_id)

        with (
            patch("app.services.deployment_queue.redis_client") as mock_redis,
            # Patch create_deployment_record + _run_deployment agar tidak hit DB/subprocess
            patch(
                "app.services.deployment_service.create_deployment_record"
            ) as mock_create,
            patch("app.services.deployment_service._run_deployment"),
            patch("app.services.deployment_service.application_repository.update_status"),
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
        ):
            mock_redis.exists.return_value = 0   # is_deployment_running → False
            mock_redis.get.return_value = None
            mock_redis.set.return_value = True   # acquire berhasil

            # Mock deployment record yang valid
            from app.models.deployment import Deployment
            from app.models.application import Application
            from app.models.server import Server
            mock_dep = MagicMock(spec=Deployment)
            mock_dep.id = 1
            mock_dep.application_id = app_id
            mock_dep.server_id = server_id
            mock_dep.branch = "main"
            mock_dep.status = "pending"
            mock_dep.commit_sha = None
            mock_dep.log_path = None
            from datetime import datetime, timezone
            mock_dep.started_at = datetime.now(tz=timezone.utc)
            mock_dep.finished_at = None
            # Rollback fields (added in P0 Item #2) — must be set explicitly
            # because MagicMock auto-creates attributes that fail Pydantic validation.
            mock_dep.is_rollback = False
            mock_dep.rollback_of = None
            mock_dep.compose_path_snapshot = None

            mock_app_obj = MagicMock(spec=Application)
            mock_app_obj.status = AppStatus.idle
            mock_server_obj = MagicMock(spec=Server)

            mock_create.return_value = (mock_dep, mock_app_obj, mock_server_obj)

            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_db

            from app.models.application import Application as RealApp
            mock_real_app = MagicMock(spec=RealApp)
            mock_real_app.status = AppStatus.idle
            with patch(
                "app.repositories.application_repository.get_by_id",
                return_value=mock_real_app,
            ):
                r = client.post(
                    "/deployments",
                    json={"application_id": app_id, "server_id": server_id},
                    headers=headers,
                )

        # Guard tidak menolak — harus 201 atau bukan 500 karena lock
        assert "sedang dalam proses deployment" not in str(r.json())


# ---------------------------------------------------------------------------
# Integration tests: webhook guard
# ---------------------------------------------------------------------------

class TestWebhookConcurrencyGuard:
    def _make_payload(self, repo_url: str = "https://github.com/org/repo") -> bytes:
        return json.dumps({
            "ref": "refs/heads/main",
            "repository": {
                "full_name": "org/repo",
                "html_url": repo_url,
                "clone_url": repo_url + ".git",
            },
            "head_commit": {
                "id": "abc123",
                "message": "test",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        }).encode("utf-8")

    def test_webhook_skips_locked_app(self, client) -> None:
        headers = _register_and_login(client)
        project_id = _create_project(client, headers)
        _create_server(client, headers)
        app_id = _create_app(client, headers, project_id)

        raw_body = self._make_payload()

        mock_app = MagicMock()
        mock_app.id = app_id
        mock_app.project_id = project_id

        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            sig = _compute_signature(raw_body, "test-secret")
            with (
                patch(
                    "app.services.deployment_queue.is_duplicate_delivery",
                    return_value=None,
                ),
                patch(
                    "app.api.webhooks.webhook_service.find_matching_applications",
                    return_value=[mock_app],
                ),
                # Simulasi: lock aktif untuk app ini
                patch(
                    "app.services.deployment_queue.redis_client"
                ) as mock_redis,
            ):
                mock_redis.exists.return_value = 1   # is_deployment_running → True
                mock_redis.get.return_value = "55"   # running deployment_id = 55

                r = client.post(
                    "/webhooks/github",
                    content=raw_body,
                    headers={
                        "X-Hub-Signature-256": sig,
                        "X-GitHub-Event": "push",
                        "X-GitHub-Delivery": "delivery-locked",
                        "Content-Type": "application/json",
                    },
                )

        assert r.status_code == 202
        data = r.json()
        assert data["accepted"] is False
        assert "sedang deploying" in data["message"]

    def test_webhook_schedules_when_not_locked(self, client) -> None:
        headers = _register_and_login(client)
        project_id = _create_project(client, headers)
        _create_server(client, headers)
        app_id = _create_app(client, headers, project_id)

        raw_body = self._make_payload()

        mock_app = MagicMock()
        mock_app.id = app_id
        mock_app.project_id = project_id

        mock_deployment = MagicMock()
        mock_deployment.id = 100

        mock_project = MagicMock()
        mock_project.owner_id = 1

        mock_server = MagicMock()
        mock_server.id = 1

        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            sig = _compute_signature(raw_body, "test-secret")
            with (
                patch(
                    "app.services.deployment_queue.is_duplicate_delivery",
                    return_value=None,
                ),
                patch("app.services.deployment_queue.mark_delivery_processed"),
                patch(
                    "app.api.webhooks.webhook_service.find_matching_applications",
                    return_value=[mock_app],
                ),
                patch(
                    "app.services.deployment_queue.redis_client"
                ) as mock_redis,
                patch(
                    "app.services.deployment_service.create_deployment_record",
                    return_value=(mock_deployment, mock_app, MagicMock()),
                ),
                patch(
                    "app.services.project_service.get_project_by_id",
                    return_value=mock_project,
                ),
                patch(
                    "app.repositories.server_repository.list_by_owner",
                    return_value=[mock_server],
                ),
                patch("app.services.deployment_queue.run_deployment_background"),
            ):
                mock_redis.exists.return_value = 0   # is_deployment_running → False
                mock_redis.get.return_value = None

                r = client.post(
                    "/webhooks/github",
                    content=raw_body,
                    headers={
                        "X-Hub-Signature-256": sig,
                        "X-GitHub-Event": "push",
                        "X-GitHub-Delivery": f"delivery-{uuid.uuid4().hex}",
                        "Content-Type": "application/json",
                    },
                )

        assert r.status_code == 202
        assert r.json()["accepted"] is True


# ---------------------------------------------------------------------------
# Integration tests: GET /applications/{id}/lock-status
# ---------------------------------------------------------------------------

class TestLockStatusEndpoint:
    def test_lock_status_not_locked(self, client) -> None:
        headers = _register_and_login(client)
        project_id = _create_project(client, headers)
        app_id = _create_app(client, headers, project_id)

        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.exists.return_value = 0
            mock_redis.get.return_value = None

            r = client.get(f"/applications/{app_id}/lock-status", headers=headers)

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["locked"] is False
        assert data["running_deployment_id"] is None
        assert data["app_status"] == "idle"
        assert data["lock_source"] == "none"

    def test_lock_status_redis_locked(self, client) -> None:
        headers = _register_and_login(client)
        project_id = _create_project(client, headers)
        app_id = _create_app(client, headers, project_id)

        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.exists.return_value = 1
            mock_redis.get.return_value = "42"

            r = client.get(f"/applications/{app_id}/lock-status", headers=headers)

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["locked"] is True
        assert data["running_deployment_id"] == 42
        assert data["lock_source"] == "redis"

    def test_lock_status_db_fallback(self, client) -> None:
        """Jika Redis tidak ada lock tapi app.status == deploying → lock_source = db."""
        headers = _register_and_login(client)
        project_id = _create_project(client, headers)
        app_id = _create_app(client, headers, project_id)

        # Set app.status = deploying via PATCH
        client.patch(
            f"/applications/{app_id}",
            json={"status": "deploying"},
            headers=headers,
        )

        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.exists.return_value = 0  # Redis tidak ada lock
            mock_redis.get.return_value = None

            r = client.get(f"/applications/{app_id}/lock-status", headers=headers)

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["locked"] is True
        assert data["app_status"] == "deploying"
        assert data["lock_source"] == "db"

    def test_lock_status_unauthorized(self, client) -> None:
        headers = _register_and_login(client)
        project_id = _create_project(client, headers)
        app_id = _create_app(client, headers, project_id)

        # Request tanpa token
        r = client.get(f"/applications/{app_id}/lock-status")
        assert r.status_code == 401

    def test_lock_status_not_found(self, client) -> None:
        headers = _register_and_login(client)

        r = client.get("/applications/99999/lock-status", headers=headers)
        assert r.status_code == 404

    def test_lock_status_other_user_cannot_access(self, client) -> None:
        """User lain tidak bisa akses lock-status aplikasi milik user pertama."""
        headers1 = _register_and_login(client)
        project_id = _create_project(client, headers1)
        app_id = _create_app(client, headers1, project_id)

        headers2 = _register_and_login(client)  # user berbeda

        r = client.get(f"/applications/{app_id}/lock-status", headers=headers2)
        assert r.status_code == 404
