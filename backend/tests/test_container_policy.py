"""Test policy resource container (limit CPU/memory & restart policy)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.container_policy import ContainerPolicy
from app.models.user import User
from app.repositories import container_policy_repository
from app.schemas.container_policy import ContainerPolicyUpsert
from app.services import auth_service, container_policy_service

PASSWORD = "password123"


def _make_container(
    name: str = "policy-web-1",
    cid: str = "abcdef1234567890",
    attrs: dict | None = None,  # type: ignore[type-arg]
) -> MagicMock:
    container = MagicMock()
    container.name = name
    container.short_id = cid[:12]
    container.id = cid
    container.status = "running"
    container.attrs = attrs if attrs is not None else _attrs(name)
    client = MagicMock()
    client.ping.return_value = True
    client.containers.get.return_value = container
    container.client = client
    return container


def _attrs(name: str) -> dict:  # type: ignore[type-arg]
    return {
        "Name": f"/{name}",
        "Id": "abcdef1234567890",
        "Config": {
            "Labels": {
                "com.docker.compose.project": "demo",
                "com.docker.compose.service": "web",
            }
        },
        "HostConfig": {
            "Memory": 0,
            "NanoCpus": 0,
            "CpuQuota": 0,
            "CpuPeriod": 0,
            "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
        },
        "State": {"Health": {"Status": "healthy"}},
    }


def _mock_client(container: MagicMock) -> MagicMock:
    client = MagicMock()
    client.ping.return_value = True
    client.containers.get.return_value = container
    client.containers.list.return_value = [container]
    container.client = client
    return client


def _create_user(db: Session, *, role: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    username = f"policy_{suffix}"
    return auth_service.create_user(
        db,
        username,
        f"{username}@example.com",
        PASSWORD,
        role=role,
    )


def _login(client: TestClient, username: str) -> str:
    response = client.post(
        "/auth/login", data={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["data"]["access_token"])


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestEffectiveLimits:
    def test_reads_nano_cpus_and_memory(self) -> None:
        attrs = _attrs("demo")
        attrs["HostConfig"].update(
            {
                "NanoCpus": 1_500_000_000,
                "Memory": 536_870_912,
                "RestartPolicy": {"Name": "unless-stopped"},
            }
        )
        limits = container_policy_service.get_effective_limits(attrs)
        assert limits.cpu_limit_cores == 1.5
        assert limits.memory_limit_bytes == 536_870_912
        assert limits.restart_policy == "unless-stopped"

    def test_reads_quota_period_pair(self) -> None:
        attrs = _attrs("demo")
        attrs["HostConfig"].update({"CpuQuota": 50_000, "CpuPeriod": 100_000})
        limits = container_policy_service.get_effective_limits(attrs)
        assert limits.cpu_limit_cores == 0.5
        assert limits.cpu_quota == 50_000

    def test_empty_hostconfig_returns_defaults(self) -> None:
        limits = container_policy_service.get_effective_limits({})
        assert limits.cpu_limit_cores is None
        assert limits.memory_limit_bytes is None
        assert limits.restart_policy == "no"


class TestBuildUpdateData:
    def test_converts_limits_and_restart_policy(self) -> None:
        policy = ContainerPolicy(
            container_name="demo",
            cpu_period=100_000,
            cpu_quota=150_000,
            memory_limit_bytes=268_435_456,
            restart_policy="always",
        )
        data = container_policy_service.build_update_data(policy)
        assert data == {
            "CpuPeriod": 100_000,
            "CpuQuota": 150_000,
            "Memory": 268_435_456,
            "RestartPolicy": {"Name": "always", "MaximumRetryCount": 0},
        }

    def test_zero_limits_sent_explicitly(self) -> None:
        policy = ContainerPolicy(container_name="demo", restart_policy="no")
        data = container_policy_service.build_update_data(policy)
        assert data["CpuQuota"] == 0
        assert data["Memory"] == 0


class TestUpsertPolicy:
    def test_creates_policy_and_applies_raw_update(self, db_session: Session) -> None:
        name = f"web-{uuid.uuid4().hex[:6]}"
        container = _make_container(name=name)
        client = _mock_client(container)
        payload = ContainerPolicyUpsert(
            cpu_limit_cores=1.5,
            memory_limit_mib=256,
            restart_policy="unless-stopped",
            auto_heal_enabled=True,
            unhealthy_threshold=2,
            max_restarts=5,
            restart_cooldown_seconds=60,
        )

        with patch(
            "app.services.container_service._get_client", return_value=client
        ):
            policy, _effective = container_policy_service.upsert_policy(
                db_session, "abcdef1234567890", payload
            )

        assert policy.container_name == name
        assert policy.cpu_quota == 150_000
        assert policy.cpu_period == 100_000
        assert policy.cpu_limit_cores == 1.5
        assert policy.memory_limit_bytes == 256 * 1024 * 1024
        assert policy.restart_policy == "unless-stopped"
        assert policy.auto_heal_enabled is True
        assert policy.unhealthy_threshold == 2
        assert policy.max_restarts == 5
        assert policy.restart_cooldown_seconds == 60
        assert policy.applied_at is not None
        assert policy.compose_project == "demo"

        client.api._post_json.assert_called_once()
        body = client.api._post_json.call_args.kwargs["data"]
        assert body["CpuQuota"] == 150_000
        assert body["Memory"] == 256 * 1024 * 1024
        assert body["RestartPolicy"]["Name"] == "unless-stopped"

    def test_updates_existing_policy_by_name(self, db_session: Session) -> None:
        name = f"web-{uuid.uuid4().hex[:6]}"
        existing = ContainerPolicy(container_name=name, cpu_period=100_000)
        db_session.add(existing)
        db_session.flush()

        container = _make_container(name=name)
        client = _mock_client(container)
        payload = ContainerPolicyUpsert(cpu_quota=200_000, apply_now=False)

        with patch(
            "app.services.container_service._get_client", return_value=client
        ):
            policy, _ = container_policy_service.upsert_policy(
                db_session, "abcdef1234567890", payload
            )

        assert policy.id == existing.id
        assert policy.cpu_quota == 200_000
        assert policy.cpu_limit_cores == 2.0
        client.api._post_json.assert_not_called()

    def test_apply_failure_persists_policy(self, db_session: Session) -> None:
        name = f"web-{uuid.uuid4().hex[:6]}"
        container = _make_container(name=name)
        client = _mock_client(container)
        client.api._post_json.side_effect = RuntimeError("engine down")

        with patch(
            "app.services.container_service._get_client", return_value=client
        ):
            with pytest.raises(RuntimeError, match="Gagal menerapkan limit"):
                container_policy_service.upsert_policy(
                    db_session,
                    "abcdef1234567890",
                    ContainerPolicyUpsert(cpu_limit_cores=1),
                )

        saved = container_policy_repository.get_by_name(db_session, name)
        assert saved is not None
        assert saved.cpu_quota == 100_000


class TestDeletePolicy:
    def test_delete_removes_row(self, db_session: Session) -> None:
        name = f"web-{uuid.uuid4().hex[:6]}"
        db_session.add(ContainerPolicy(container_name=name))
        db_session.flush()
        container = _make_container(name=name)
        client = _mock_client(container)

        with patch(
            "app.services.container_service._get_client", return_value=client
        ):
            deleted = container_policy_service.delete_policy(
                db_session, "abcdef1234567890"
            )

        assert deleted == name
        assert container_policy_repository.get_by_name(db_session, name) is None

    def test_delete_does_not_touch_docker_limits(self, db_session: Session) -> None:
        name = f"web-{uuid.uuid4().hex[:6]}"
        db_session.add(
            ContainerPolicy(container_name=name, cpu_quota=100_000, cpu_period=100_000)
        )
        db_session.flush()
        container = _make_container(name=name)
        client = _mock_client(container)

        with patch(
            "app.services.container_service._get_client", return_value=client
        ):
            container_policy_service.delete_policy(db_session, "abcdef1234567890")

        client.api._post_json.assert_not_called()

    def test_delete_missing_policy_raises(self, db_session: Session) -> None:
        name = f"web-{uuid.uuid4().hex[:6]}"
        container = _make_container(name=name)
        client = _mock_client(container)
        with patch(
            "app.services.container_service._get_client", return_value=client
        ):
            with pytest.raises(ValueError, match="tidak ditemukan"):
                container_policy_service.delete_policy(
                    db_session, "abcdef1234567890"
                )


class TestReapply:
    def test_reapply_for_container_applies_saved_policy(
        self, db_session: Session
    ) -> None:
        name = f"web-{uuid.uuid4().hex[:6]}"
        policy = ContainerPolicy(
            container_name=name,
            cpu_quota=50_000,
            cpu_period=100_000,
            memory_limit_bytes=1024,
        )
        db_session.add(policy)
        db_session.flush()

        class _Ctx:
            def __enter__(self) -> Session:
                return db_session

            def __exit__(self, *args: object) -> None:
                return None

        with (
            patch(
                "app.services.container_policy_service.SessionLocal",
                return_value=_Ctx(),
            ),
            patch("app.services.container_policy_service.apply_policy") as apply,
        ):
            result = container_policy_service.reapply_for_container(name)

        assert result is True
        apply.assert_called_once()

    def test_reapply_returns_false_when_no_policy(self) -> None:
        class _Ctx:
            def __enter__(self) -> MagicMock:
                db = MagicMock(spec=Session)
                db.execute.return_value.scalar_one_or_none.return_value = None
                return db

            def __exit__(self, *args: object) -> None:
                return None

        with patch(
            "app.services.container_policy_service.SessionLocal",
            return_value=_Ctx(),
        ):
            assert container_policy_service.reapply_for_container("absent") is False

    def test_start_container_reapplies_policy(self) -> None:
        container = _make_container()
        client = _mock_client(container)
        with (
            patch(
                "app.services.container_service._get_client", return_value=client
            ),
            patch(
                "app.services.container_policy_service.reapply_for_container"
            ) as reapply,
        ):
            from app.services.container_service import start_container

            start_container("abcdef1234567890")

        container.start.assert_called_once()
        reapply.assert_called_once_with(container.name)


class TestPolicyApi:
    def test_get_policy_without_row(self, client: TestClient, db_session: Session) -> None:
        user = _create_user(db_session, role="viewer")
        token = _login(client, user.username)
        name = f"web-{uuid.uuid4().hex[:6]}"
        container = _make_container(name=name)
        docker_client = _mock_client(container)

        with patch(
            "app.services.container_service._get_client", return_value=docker_client
        ):
            response = client.get(
                f"/containers/{container.id}/policy", headers=_headers(token)
            )

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["policy"] is None
        assert data["container_name"] == name
        assert data["effective"]["restart_policy"] == "no"

    def test_put_policy_requires_lifecycle_permission(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role="viewer")
        token = _login(client, user.username)
        container = _make_container()

        response = client.put(
            f"/containers/{container.id}/policy",
            json={"cpu_limit_cores": 1, "memory_limit_mib": 128},
            headers=_headers(token),
        )
        assert response.status_code == 403, response.text

    def test_put_policy_success_and_get_detail(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role="developer")
        token = _login(client, user.username)
        name = f"web-{uuid.uuid4().hex[:6]}"
        container = _make_container(name=name)
        docker_client = _mock_client(container)

        with patch(
            "app.services.container_service._get_client", return_value=docker_client
        ):
            put = client.put(
                f"/containers/{container.id}/policy",
                json={
                    "cpu_limit_cores": 0.5,
                    "memory_limit_mib": 128,
                    "restart_policy": "always",
                    "auto_heal_enabled": True,
                    "unhealthy_threshold": 2,
                },
                headers=_headers(token),
            )
            assert put.status_code == 200, put.text
            body = put.json()["data"]
            assert body["policy"]["container_name"] == name
            assert body["policy"]["cpu_quota"] == 50_000
            assert body["policy"]["memory_limit_bytes"] == 128 * 1024 * 1024
            assert body["message"] == "Policy container disimpan"

            detail = client.get(
                f"/containers/{container.id}/policy", headers=_headers(token)
            )

        assert detail.status_code == 200, detail.text
        detail_data = detail.json()["data"]
        assert detail_data["policy"]["restart_policy"] == "always"
        assert detail_data["policy"]["auto_heal_enabled"] is True
        assert detail_data["compose_project"] == "demo"

    def test_put_policy_apply_failure_returns_502(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role="admin")
        token = _login(client, user.username)
        container = _make_container()
        docker_client = _mock_client(container)
        docker_client.api._post_json.side_effect = RuntimeError("engine down")

        with patch(
            "app.services.container_service._get_client", return_value=docker_client
        ):
            response = client.put(
                f"/containers/{container.id}/policy",
                json={"cpu_limit_cores": 1},
                headers=_headers(token),
            )

        assert response.status_code == 502, response.text
        assert "Policy tersimpan" in response.json()["message"]

    def test_delete_missing_policy_returns_404(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role="developer")
        token = _login(client, user.username)
        name = f"web-{uuid.uuid4().hex[:6]}"
        container = _make_container(name=name)
        docker_client = _mock_client(container)

        with patch(
            "app.services.container_service._get_client", return_value=docker_client
        ):
            response = client.delete(
                f"/containers/{container.id}/policy", headers=_headers(token)
            )

        assert response.status_code == 404, response.text
