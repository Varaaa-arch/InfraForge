"""
Test untuk GitHub Webhook Handler & Deployment Queue (Milestone 3 — P0).

Coverage:
  - Signature validation (HMAC SHA-256 constant-time comparison)
  - Event filtering (hanya 'push' yang diproses)
  - Branch extraction dari ref
  - Idempotency via X-GitHub-Delivery dedup
  - Application matching by repository URL + branch
  - Redis lock (SETNX) untuk mencegah concurrent deploy
  - Endpoint integration: 202 Accepted, 401, 500

Semua Redis interaction di-mock — tidak perlu Redis nyata.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.services import webhook_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_signature(raw_body: bytes, secret: str) -> str:
    """Compute valid HMAC SHA-256 signature untuk testing."""
    digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def _make_push_payload(
    ref: str = "refs/heads/main",
    repo_url: str = "https://github.com/org/repo",
    commit_sha: str = "abc123def456",
) -> dict:
    """Buat GitHub push event payload untuk testing."""
    return {
        "ref": ref,
        "repository": {
            "full_name": "org/repo",
            "html_url": repo_url,
            "clone_url": repo_url + ".git",
        },
        "head_commit": {
            "id": commit_sha,
            "message": "test commit",
            "timestamp": "2024-01-01T00:00:00Z",
        },
    }


# ---------------------------------------------------------------------------
# verify_signature
# ---------------------------------------------------------------------------

class TestVerifySignature:
    def test_valid_signature(self) -> None:
        body = b'{"ref":"refs/heads/main"}'
        secret = "test-secret"
        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", secret):
            sig = _compute_signature(body, secret)
            assert webhook_service.verify_signature(body, sig) is True

    def test_invalid_signature(self) -> None:
        body = b'{"ref":"refs/heads/main"}'
        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            result = webhook_service.verify_signature(body, "sha256=invalid")
            assert result is False

    def test_missing_signature_header(self) -> None:
        body = b'{"ref":"refs/heads/main"}'
        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            assert webhook_service.verify_signature(body, None) is False

    def test_empty_secret_returns_false(self) -> None:
        body = b'{"ref":"refs/heads/main"}'
        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", ""):
            sig = _compute_signature(body, "old-secret")
            assert webhook_service.verify_signature(body, sig) is False

    def test_wrong_secret_returns_false(self) -> None:
        body = b'{"ref":"refs/heads/main"}'
        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "correct-secret"):
            sig = _compute_signature(body, "wrong-secret")
            assert webhook_service.verify_signature(body, sig) is False

    def test_tampered_body_returns_false(self) -> None:
        body = b'{"ref":"refs/heads/main"}'
        secret = "test-secret"
        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", secret):
            sig = _compute_signature(body, secret)
            # Tamper body
            tampered = b'{"ref":"refs/heads/dev"}'
            assert webhook_service.verify_signature(tampered, sig) is False

    def test_missing_sha256_prefix(self) -> None:
        body = b'{"ref":"refs/heads/main"}'
        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            assert webhook_service.verify_signature(body, "sha1=abc123") is False


# ---------------------------------------------------------------------------
# extract_branch
# ---------------------------------------------------------------------------

class TestExtractBranch:
    def test_branch_ref(self) -> None:
        assert webhook_service.extract_branch("refs/heads/main") == "main"

    def test_nested_branch(self) -> None:
        assert webhook_service.extract_branch("refs/heads/feature/auth") == "feature/auth"

    def test_tag_ref_returns_none(self) -> None:
        assert webhook_service.extract_branch("refs/tags/v1.0") is None

    def test_unknown_ref_returns_none(self) -> None:
        assert webhook_service.extract_branch("unknown") is None


# ---------------------------------------------------------------------------
# _normalize_repo_url
# ---------------------------------------------------------------------------

class TestNormalizeRepoUrl:
    def test_strips_trailing_slash(self) -> None:
        result = webhook_service._normalize_repo_url("https://github.com/org/repo/")
        assert result == "https://github.com/org/repo"

    def test_strips_git_suffix(self) -> None:
        result = webhook_service._normalize_repo_url("https://github.com/org/repo.git")
        assert result == "https://github.com/org/repo"

    def test_lowercases(self) -> None:
        result = webhook_service._normalize_repo_url("https://github.com/Org/Repo")
        assert result == "https://github.com/org/repo"

    def test_idempotent(self) -> None:
        url1 = webhook_service._normalize_repo_url("https://github.com/org/repo")
        url2 = webhook_service._normalize_repo_url("https://github.com/org/repo.git/")
        assert url1 == url2


# ---------------------------------------------------------------------------
# find_matching_applications
# ---------------------------------------------------------------------------

class TestFindMatchingApplications:
    def test_match_same_url_and_branch(self) -> None:
        from app.models.application import Application
        app = MagicMock(spec=Application)
        app.repository = "https://github.com/org/repo.git"
        app.branch = "main"

        db = MagicMock()
        with patch(
            "app.services.webhook_service.application_repository.list_all_with_repository",
            return_value=[app],
        ):
            result = webhook_service.find_matching_applications(
                db, "https://github.com/org/repo", "main"
            )
        assert len(result) == 1
        assert result[0] is app

    def test_no_match_different_branch(self) -> None:
        from app.models.application import Application
        app = MagicMock(spec=Application)
        app.repository = "https://github.com/org/repo.git"
        app.branch = "main"

        db = MagicMock()
        with patch(
            "app.services.webhook_service.application_repository.list_all_with_repository",
            return_value=[app],
        ):
            result = webhook_service.find_matching_applications(
                db, "https://github.com/org/repo", "develop"
            )
        assert len(result) == 0

    def test_no_match_different_url(self) -> None:
        from app.models.application import Application
        app = MagicMock(spec=Application)
        app.repository = "https://github.com/org/repo.git"
        app.branch = "main"

        db = MagicMock()
        with patch(
            "app.services.webhook_service.application_repository.list_all_with_repository",
            return_value=[app],
        ):
            result = webhook_service.find_matching_applications(
                db, "https://github.com/other/repo", "main"
            )
        assert len(result) == 0

    def test_match_with_trailing_slash_normalization(self) -> None:
        from app.models.application import Application
        app = MagicMock(spec=Application)
        app.repository = "https://github.com/org/repo/"
        app.branch = "main"

        db = MagicMock()
        with patch(
            "app.services.webhook_service.application_repository.list_all_with_repository",
            return_value=[app],
        ):
            result = webhook_service.find_matching_applications(
                db, "https://github.com/org/repo", "main"
            )
        assert len(result) == 1

    def test_multiple_matching_apps(self) -> None:
        from app.models.application import Application
        app1 = MagicMock(spec=Application)
        app1.repository = "https://github.com/org/repo"
        app1.branch = "main"
        app2 = MagicMock(spec=Application)
        app2.repository = "https://github.com/org/repo.git"
        app2.branch = "main"

        db = MagicMock()
        with patch(
            "app.services.webhook_service.application_repository.list_all_with_repository",
            return_value=[app1, app2],
        ):
            result = webhook_service.find_matching_applications(
                db, "https://github.com/org/repo", "main"
            )
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Deployment queue: Redis lock & idempotency
# ---------------------------------------------------------------------------

class TestDeploymentQueueLock:
    def test_lock_key_format(self) -> None:
        from app.services.deployment_queue import _lock_key
        assert _lock_key(42) == "infraforge:deploy:lock:42"

    def test_dedup_key_format(self) -> None:
        from app.services.deployment_queue import _dedup_key
        assert _dedup_key("abc-123") == "infraforge:webhook:dedup:abc-123"

    def test_is_deployment_running_when_lock_exists(self) -> None:
        from app.services import deployment_queue
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.exists.return_value = 1
            assert deployment_queue.is_deployment_running(42) is True

    def test_is_deployment_running_when_lock_absent(self) -> None:
        from app.services import deployment_queue
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.exists.return_value = 0
            assert deployment_queue.is_deployment_running(42) is False

    def test_is_duplicate_delivery_when_exists(self) -> None:
        from app.services import deployment_queue
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.get.return_value = "123"
            result = deployment_queue.is_duplicate_delivery("delivery-abc")
            assert result == 123

    def test_is_duplicate_delivery_when_absent(self) -> None:
        from app.services import deployment_queue
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            mock_redis.get.return_value = None
            result = deployment_queue.is_duplicate_delivery("delivery-abc")
            assert result is None

    def test_is_duplicate_delivery_empty_id_returns_none(self) -> None:
        from app.services import deployment_queue
        result = deployment_queue.is_duplicate_delivery("")
        assert result is None

    def test_mark_delivery_processed_calls_redis(self) -> None:
        from app.services import deployment_queue
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            deployment_queue.mark_delivery_processed("delivery-abc", 42)
            mock_redis.setex.assert_called_once()
            args = mock_redis.setex.call_args
            assert args[0][0] == "infraforge:webhook:dedup:delivery-abc"
            assert args[0][2] == "42"

    def test_mark_delivery_processed_skips_empty_id(self) -> None:
        from app.services import deployment_queue
        with patch("app.services.deployment_queue.redis_client") as mock_redis:
            deployment_queue.mark_delivery_processed("", 42)
            mock_redis.setex.assert_not_called()


# ---------------------------------------------------------------------------
# Deployment queue: run_deployment_background (sync background task)
# ---------------------------------------------------------------------------

class TestRunDeploymentTask:
    def test_skipped_when_lock_not_acquired(self) -> None:
        from app.services.deployment_queue import run_deployment_background
        from app.models.deployment import Deployment

        mock_dep = MagicMock(spec=Deployment)

        with (
            patch("app.services.deployment_queue.redis_client") as mock_redis,
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
            patch("app.repositories.deployment_repository.get_by_id", return_value=mock_dep),
            patch("app.repositories.deployment_repository.update_status"),
        ):
            mock_redis.set.return_value = False   # Lock not acquired
            mock_redis.get.return_value = "77"    # running deployment_id

            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_db

            run_deployment_background(1, 1, 1)

            # SessionLocal DIPANGGIL (untuk mark deployment failed),
            # tapi lock harus tidak di-delete (karena tidak pernah di-acquire)
            mock_session_cls.assert_called_once()
            mock_redis.delete.assert_not_called()

    def test_failed_when_deployment_not_found(self) -> None:
        from app.services.deployment_queue import run_deployment_background
        with (
            patch("app.services.deployment_queue.redis_client") as mock_redis,
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
            patch("app.repositories.deployment_repository.get_by_id", return_value=None),
        ):
            mock_redis.set.return_value = True
            mock_redis.delete.return_value = 1

            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_db

            run_deployment_background(999, 1, 1)

            # Lock harus di-release via finally block
            mock_redis.delete.assert_called_once()

    def test_lock_released_in_finally(self) -> None:
        from app.services.deployment_queue import run_deployment_background
        with (
            patch("app.services.deployment_queue.redis_client") as mock_redis,
            patch("app.services.deployment_queue.SessionLocal") as mock_session_cls,
            patch(
                "app.repositories.deployment_repository.get_by_id",
                side_effect=Exception("DB error"),
            ),
        ):
            mock_redis.set.return_value = True
            mock_redis.delete.return_value = 1
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db

            run_deployment_background(1, 1, 1)

            mock_redis.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Webhook API endpoint integration tests
# ---------------------------------------------------------------------------

class TestWebhookEndpoint:
    """Test endpoint HTTP — pakai TestClient + DB rollback dari conftest."""

    def _register_and_login(self, client: object) -> dict[str, str]:
        import uuid
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        suffix = uuid.uuid4().hex[:8]
        user = {
            "username": f"wh_{suffix}",
            "email": f"wh_{suffix}@x.com",
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
        self,
        client: object,
        headers: dict[str, str],
        project_id: int,
        repo_url: str = "https://github.com/org/repo",
        branch: str = "main",
    ) -> int:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.post(
            "/applications",
            json={
                "project_id": project_id,
                "name": "test-app",
                "repository": repo_url,
                "branch": branch,
            },
            headers=headers,
        )
        return int(r.json()["data"]["id"])

    def test_valid_webhook_returns_202(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._register_and_login(c)
        project_id = self._create_project(c, headers)
        server_id = self._create_server(c, headers)
        app_id = self._create_app(c, headers, project_id)

        payload = _make_push_payload(repo_url="https://github.com/org/repo")
        raw_body = json.dumps(payload).encode("utf-8")

        # Mock app that would be found by find_matching_applications.
        # We can't rely on the real DB because the webhook handler opens its
        # own DB session via next(get_db()), which is outside the test's
        # transaction savepoint.
        mock_app = MagicMock()
        mock_app.id = app_id
        mock_app.project_id = project_id

        mock_deployment = MagicMock()
        mock_deployment.id = 999

        mock_project = MagicMock()
        mock_project.owner_id = 1

        mock_server = MagicMock()
        mock_server.id = server_id

        with (
            patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"),
        ):
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
                patch(
                    "app.services.deployment_queue.run_deployment_background",
                ),
            ):
                r = c.post(
                    "/webhooks/github",
                    content=raw_body,
                    headers={
                        "X-Hub-Signature-256": sig,
                        "X-GitHub-Event": "push",
                        "X-GitHub-Delivery": "delivery-abc",
                        "Content-Type": "application/json",
                    },
                )

        assert r.status_code == 202
        data = r.json()
        assert data["accepted"] is True
        assert data["deployment_id"] is not None

    def test_invalid_signature_returns_401(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        payload = _make_push_payload()
        raw_body = json.dumps(payload).encode("utf-8")

        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            r = c.post(
                "/webhooks/github",
                content=raw_body,
                headers={
                    "X-Hub-Signature-256": "sha256=invalid",
                    "X-GitHub-Event": "push",
                    "X-GitHub-Delivery": "delivery-abc",
                    "Content-Type": "application/json",
                },
            )
        assert r.status_code == 401

    def test_missing_secret_returns_500(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        payload = _make_push_payload()
        raw_body = json.dumps(payload).encode("utf-8")

        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", ""):
            r = c.post(
                "/webhooks/github",
                content=raw_body,
                headers={
                    "X-Hub-Signature-256": "sha256=abc",
                    "X-GitHub-Event": "push",
                    "X-GitHub-Delivery": "delivery-abc",
                    "Content-Type": "application/json",
                },
            )
        assert r.status_code == 500

    def test_non_push_event_returns_202_with_accepted_false(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        payload = _make_push_payload()
        raw_body = json.dumps(payload).encode("utf-8")

        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            sig = _compute_signature(raw_body, "test-secret")
            r = c.post(
                "/webhooks/github",
                content=raw_body,
                headers={
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "ping",
                    "X-GitHub-Delivery": "delivery-ping",
                    "Content-Type": "application/json",
                },
            )
        assert r.status_code == 202
        data = r.json()
        assert data["accepted"] is False

    def test_tag_push_returns_202_with_accepted_false(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        payload = _make_push_payload(ref="refs/tags/v1.0")
        raw_body = json.dumps(payload).encode("utf-8")

        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            sig = _compute_signature(raw_body, "test-secret")
            r = c.post(
                "/webhooks/github",
                content=raw_body,
                headers={
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "push",
                    "X-GitHub-Delivery": "delivery-tag",
                    "Content-Type": "application/json",
                },
            )
        assert r.status_code == 202
        data = r.json()
        assert data["accepted"] is False

    def test_duplicate_delivery_returns_202_with_accepted_false(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        payload = _make_push_payload()
        raw_body = json.dumps(payload).encode("utf-8")

        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            sig = _compute_signature(raw_body, "test-secret")
            with patch(
                "app.services.deployment_queue.is_duplicate_delivery",
                return_value=42,
            ):
                r = c.post(
                    "/webhooks/github",
                    content=raw_body,
                    headers={
                        "X-Hub-Signature-256": sig,
                        "X-GitHub-Event": "push",
                        "X-GitHub-Delivery": "delivery-dup",
                        "Content-Type": "application/json",
                    },
                )
        assert r.status_code == 202
        data = r.json()
        assert data["accepted"] is False
        assert data["deployment_id"] == 42

    def test_no_matching_app_returns_202_with_accepted_false(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]

        payload = _make_push_payload(
            repo_url="https://github.com/org/nonexistent"
        )
        raw_body = json.dumps(payload).encode("utf-8")

        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            sig = _compute_signature(raw_body, "test-secret")
            with (
                patch(
                    "app.services.deployment_queue.is_duplicate_delivery",
                    return_value=None,
                ),
                patch(
                    "app.api.webhooks.webhook_service.find_matching_applications",
                    return_value=[],
                ),
            ):
                r = c.post(
                    "/webhooks/github",
                    content=raw_body,
                    headers={
                        "X-Hub-Signature-256": sig,
                        "X-GitHub-Event": "push",
                        "X-GitHub-Delivery": "delivery-nomatch",
                        "Content-Type": "application/json",
                    },
                )
        assert r.status_code == 202
        data = r.json()
        assert data["accepted"] is False

    def test_invalid_json_returns_400(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        raw_body = b"not json at all"

        with patch.object(settings, "GITHUB_WEBHOOK_SECRET", "test-secret"):
            sig = _compute_signature(raw_body, "test-secret")
            r = c.post(
                "/webhooks/github",
                content=raw_body,
                headers={
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "push",
                    "X-GitHub-Delivery": "delivery-badjson",
                    "Content-Type": "application/json",
                },
            )
        assert r.status_code == 400
