"""
Test untuk endpoint environment variable versi Fase 2:
- `PATCH /projects/{id}/env/{env_id}` (ubah nilai satu variabel)
- Indikator `pending_redeploy` + `last_deployment_at` pada list env var
- Audit log saat nilai rahasia di-reveal
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.repositories import deployment_repository


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


def _create_project(client: TestClient, tokens: dict[str, str], name: str) -> dict:
    r = client.post("/projects", headers=_auth(tokens), json={"name": name})
    assert r.status_code == 201
    return dict(r.json()["data"])


def _create_application(client: TestClient, tokens: dict[str, str], project_id: int) -> dict:
    r = client.post(
        "/applications",
        headers=_auth(tokens),
        json={"project_id": project_id, "name": "demo-app"},
    )
    assert r.status_code == 201
    return dict(r.json()["data"])


def _env_url(project_id: int) -> str:
    return f"/projects/{project_id}/env"


def _upsert_env(client: TestClient, tokens: dict[str, str], project_id: int, key: str, value: str) -> dict:
    r = client.post(
        _env_url(project_id),
        headers=_auth(tokens),
        json={"env_vars": [{"key": key, "value": value}]},
    )
    assert r.status_code == 200
    return dict(r.json()["data"]["env_vars"][0])


def _create_deployment(
    db: Session, application_id: int, started_at: datetime
) -> None:
    """Buat deployment dengan waktu mulai yang dikontrol."""
    deployment = deployment_repository.create(db, application_id, None, "main")
    deployment.started_at = started_at
    db.commit()


# ---------------------------------------------------------------------------
# PATCH env var
# ---------------------------------------------------------------------------

class TestUpdateEnvVar:
    def test_patch_updates_value_and_returns_masked(
        self, client: TestClient
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens, "patch-project")
        created = _upsert_env(client, tokens, project["id"], "SECRET", "old-value")

        r = client.patch(
            f"{_env_url(project['id'])}/{created['id']}",
            headers=_auth(tokens),
            json={"value": "brand-new-value"},
        )

        assert r.status_code == 200
        item = r.json()["data"]
        assert item["key"] == "SECRET"
        assert item["masked_value"] == "bra****"
        assert "value" not in item

        # Nilai terbaru tersimpan terenkripsi & terbaca saat reveal
        reveal = client.get(
            f"{_env_url(project['id'])}/{created['id']}", headers=_auth(tokens)
        )
        assert reveal.json()["data"]["value"] == "brand-new-value"

    def test_patch_unknown_env_var_returns_404(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens, "patch-missing-project")

        r = client.patch(
            f"{_env_url(project['id'])}/99999999",
            headers=_auth(tokens),
            json={"value": "whatever"},
        )

        assert r.status_code == 404

    def test_patch_env_var_of_other_project_returns_404(
        self, client: TestClient
    ) -> None:
        tokens_a = _register_and_login(client, _unique_user())
        tokens_b = _register_and_login(client, _unique_user())
        project_a = _create_project(client, tokens_a, "owner-a-project")
        project_b = _create_project(client, tokens_b, "owner-b-project")
        created = _upsert_env(client, tokens_a, project_a["id"], "SECRET", "value-a")

        r = client.patch(
            f"{_env_url(project_b['id'])}/{created['id']}",
            headers=_auth(tokens_b),
            json={"value": "hijacked"},
        )

        assert r.status_code == 404

    def test_patch_empty_value_returns_422(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens, "patch-empty-project")
        created = _upsert_env(client, tokens, project["id"], "SECRET", "value")

        r = client.patch(
            f"{_env_url(project['id'])}/{created['id']}",
            headers=_auth(tokens),
            json={"value": ""},
        )

        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Indikator re-deploy
# ---------------------------------------------------------------------------

class TestRedeployIndicator:
    def test_last_deployment_at_is_null_without_deployment(
        self, client: TestClient
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens, "no-deploy-project")
        _upsert_env(client, tokens, project["id"], "SECRET", "value")

        r = client.get(_env_url(project["id"]), headers=_auth(tokens))

        assert r.status_code == 200
        body = r.json()["data"]
        assert body["last_deployment_at"] is None
        assert body["env_vars"][0]["pending_redeploy"] is False

    def test_env_var_changed_after_deployment_needs_redeploy(
        self, client: TestClient, db_session: Session
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens, "redeploy-project")
        application = _create_application(client, tokens, project["id"])
        _create_deployment(
            db_session,
            application["id"],
            datetime.now(tz=UTC) - timedelta(hours=2),
        )
        _upsert_env(client, tokens, project["id"], "SECRET", "value")

        r = client.get(_env_url(project["id"]), headers=_auth(tokens))

        body = r.json()["data"]
        assert body["last_deployment_at"] is not None
        assert body["env_vars"][0]["pending_redeploy"] is True

    def test_env_var_older_than_deployment_is_settled(
        self, client: TestClient, db_session: Session
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens, "settled-project")
        application = _create_application(client, tokens, project["id"])
        _upsert_env(client, tokens, project["id"], "SECRET", "value")
        # Deployment terjadi setelah env var dibuat → env var sudah terpasang
        _create_deployment(
            db_session,
            application["id"],
            datetime.now(tz=UTC) + timedelta(hours=1),
        )

        r = client.get(_env_url(project["id"]), headers=_auth(tokens))

        body = r.json()["data"]
        assert body["env_vars"][0]["pending_redeploy"] is False

    def test_deployment_of_other_project_does_not_affect(
        self, client: TestClient, db_session: Session
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens, "isolated-deploy-project")
        other = _create_project(client, tokens, "other-deploy-project")
        application = _create_application(client, tokens, other["id"])
        _create_deployment(
            db_session,
            application["id"],
            datetime.now(tz=UTC) + timedelta(hours=5),
        )
        _upsert_env(client, tokens, project["id"], "SECRET", "value")

        r = client.get(_env_url(project["id"]), headers=_auth(tokens))

        body = r.json()["data"]
        assert body["last_deployment_at"] is None
        assert body["env_vars"][0]["pending_redeploy"] is False

    def test_patch_marks_env_var_as_pending_redeploy(
        self, client: TestClient, db_session: Session
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens, "patch-redeploy-project")
        application = _create_application(client, tokens, project["id"])
        _create_deployment(
            db_session,
            application["id"],
            datetime.now(tz=UTC) - timedelta(hours=2),
        )
        created = _upsert_env(client, tokens, project["id"], "SECRET", "value")

        r = client.patch(
            f"{_env_url(project['id'])}/{created['id']}",
            headers=_auth(tokens),
            json={"value": "new-value"},
        )

        assert r.status_code == 200
        assert r.json()["data"]["pending_redeploy"] is True


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class TestRevealAudit:
    def test_reveal_logs_audit_event(
        self, client: TestClient, log_sink: list[str]
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens, "audit-project")
        created = _upsert_env(client, tokens, project["id"], "SECRET", "value")

        client.get(f"{_env_url(project['id'])}/{created['id']}", headers=_auth(tokens))

        assert any("REVEAL_ENV_VAR" in message for message in log_sink)

    def test_update_logs_audit_event(
        self, client: TestClient, log_sink: list[str]
    ) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens, "audit-update-project")
        created = _upsert_env(client, tokens, project["id"], "SECRET", "value")

        client.patch(
            f"{_env_url(project['id'])}/{created['id']}",
            headers=_auth(tokens),
            json={"value": "changed"},
        )

        assert any("UPDATE_ENV_VAR" in message for message in log_sink)
