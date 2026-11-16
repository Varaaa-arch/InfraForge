"""Test auto-healing container: keputusan, poller, audit, dan API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from docker.errors import NotFound
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.container_policy import ContainerPolicy
from app.models.user import User
from app.services import audit_service, auth_service, auto_heal_service

PASSWORD = "password123"
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _enable_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_service, "AUDIT_PERSIST_ENABLED", True)


def _make_policy(
    db: Session,
    *,
    name: str | None = None,
    unhealthy_streak: int = 0,
    last_health_status: str | None = None,
    last_restart_at: datetime | None = None,
    restart_count_window: int = 0,
    window_started_at: datetime | None = None,
    **kwargs: object,
) -> ContainerPolicy:
    policy = ContainerPolicy(
        container_name=name or f"auto-{uuid.uuid4().hex[:6]}",
        auto_heal_enabled=kwargs.pop("auto_heal_enabled", True),
        unhealthy_threshold=kwargs.pop("unhealthy_threshold", 3),
        max_restarts=kwargs.pop("max_restarts", 3),
        restart_cooldown_seconds=kwargs.pop("restart_cooldown_seconds", 300),
        unhealthy_streak=unhealthy_streak,
        last_health_status=last_health_status,
        last_restart_at=last_restart_at,
        restart_count_window=restart_count_window,
        window_started_at=window_started_at,
        **kwargs,
    )
    db.add(policy)
    db.flush()
    return policy


def _snapshot(health: str | None, status: str = "running") -> auto_heal_service.HealthSnapshot:
    return auto_heal_service.HealthSnapshot(status=status, health=health)


def _container(name: str, health: str | None) -> MagicMock:
    container = MagicMock()
    container.name = name
    container.id = "cid-" + name
    container.status = "running"
    container.attrs = {
        "Name": f"/{name}",
        "State": {"Health": {"Status": health}} if health else {},
    }
    return container


def _client_for(container: MagicMock | None, *, error: Exception | None = None) -> MagicMock:
    client = MagicMock()
    if error is not None:
        client.containers.get.side_effect = error
    else:
        client.containers.get.return_value = container
    return client


def _audit_actions(db: Session) -> list[str]:
    return list(
        db.execute(
            select(AuditLog.action).order_by(AuditLog.id)
        ).scalars()
    )


class TestDecideAction:
    def test_unhealthy_below_threshold_records_streak(self) -> None:
        policy = ContainerPolicy(
            container_name="x", unhealthy_threshold=3, unhealthy_streak=0
        )
        decision = auto_heal_service.decide_action(policy, _snapshot("unhealthy"), now=NOW)
        assert decision.action == auto_heal_service.DECISION_RECORD_UNHEALTHY
        assert decision.streak == 1

    def test_unhealthy_reaching_threshold_restarts(self) -> None:
        policy = ContainerPolicy(
            container_name="x", unhealthy_threshold=2, unhealthy_streak=1
        )
        decision = auto_heal_service.decide_action(policy, _snapshot("unhealthy"), now=NOW)
        assert decision.action == auto_heal_service.DECISION_RESTART
        assert decision.streak == 2

    def test_cooldown_blocks_restart(self) -> None:
        policy = ContainerPolicy(
            container_name="x",
            unhealthy_threshold=1,
            unhealthy_streak=5,
            restart_cooldown_seconds=300,
            last_restart_at=NOW - timedelta(seconds=10),
        )
        decision = auto_heal_service.decide_action(policy, _snapshot("unhealthy"), now=NOW)
        assert decision.action == auto_heal_service.DECISION_NOOP
        assert "cooldown" in decision.reason

    def test_max_restarts_in_window_blocks(self) -> None:
        policy = ContainerPolicy(
            container_name="x",
            unhealthy_threshold=1,
            max_restarts=2,
            restart_count_window=2,
            window_started_at=NOW - timedelta(minutes=5),
        )
        decision = auto_heal_service.decide_action(
            policy, _snapshot("unhealthy"), now=NOW, window_minutes=60
        )
        assert decision.action == auto_heal_service.DECISION_NOOP
        assert "batas restart" in decision.reason

    def test_expired_window_resets_restart_budget(self) -> None:
        policy = ContainerPolicy(
            container_name="x",
            unhealthy_threshold=1,
            max_restarts=2,
            restart_count_window=2,
            window_started_at=NOW - timedelta(minutes=90),
        )
        decision = auto_heal_service.decide_action(
            policy, _snapshot("unhealthy"), now=NOW, window_minutes=60
        )
        assert decision.action == auto_heal_service.DECISION_RESTART
        assert decision.restarts_in_window == 0

    def test_zero_max_restarts_disables_restart(self) -> None:
        policy = ContainerPolicy(
            container_name="x", unhealthy_threshold=1, max_restarts=0
        )
        decision = auto_heal_service.decide_action(policy, _snapshot("unhealthy"), now=NOW)
        assert decision.action == auto_heal_service.DECISION_NOOP

    def test_healthy_after_unhealthy_records_recovery(self) -> None:
        policy = ContainerPolicy(
            container_name="x",
            unhealthy_streak=2,
            last_health_status="unhealthy",
        )
        decision = auto_heal_service.decide_action(policy, _snapshot("healthy"), now=NOW)
        assert decision.action == auto_heal_service.DECISION_RECORD_RECOVERED

    def test_healthy_with_previous_restart_records_recovery(self) -> None:
        policy = ContainerPolicy(
            container_name="x",
            unhealthy_streak=0,
            last_health_status="unhealthy",
            restart_count_window=1,
            last_restart_at=NOW - timedelta(seconds=5),
        )
        decision = auto_heal_service.decide_action(policy, _snapshot("healthy"), now=NOW)
        assert decision.action == auto_heal_service.DECISION_RECORD_RECOVERED

    def test_starting_or_missing_health_is_noop(self) -> None:
        policy = ContainerPolicy(container_name="x", unhealthy_streak=1)
        assert (
            auto_heal_service.decide_action(policy, _snapshot("starting"), now=NOW).action
            == auto_heal_service.DECISION_NOOP
        )
        assert (
            auto_heal_service.decide_action(policy, _snapshot(None), now=NOW).action
            == auto_heal_service.DECISION_NOOP
        )


class TestPollOnce:
    def test_records_unhealthy_event(self, db_session: Session) -> None:
        policy = _make_policy(db_session, unhealthy_threshold=3)
        container = _container(policy.container_name, "unhealthy")

        with patch(
            "app.services.container_service._get_client",
            return_value=_client_for(container),
        ):
            stats = auto_heal_service.poll_once(db_session, now=NOW)

        assert stats["unhealthy"] == 1
        assert stats["restarted"] == 0
        assert policy.unhealthy_streak == 1
        assert policy.last_health_status == "unhealthy"
        assert "CONTAINER_UNHEALTHY" in _audit_actions(db_session)
        container.restart.assert_not_called()

    def test_restarts_after_threshold_and_audits(self, db_session: Session) -> None:
        policy = _make_policy(db_session, unhealthy_threshold=1, restart_cooldown_seconds=0)
        container = _container(policy.container_name, "unhealthy")

        with patch(
            "app.services.container_service._get_client",
            return_value=_client_for(container),
        ):
            stats = auto_heal_service.poll_once(db_session, now=NOW)

        assert stats["restarted"] == 1
        container.restart.assert_called_once_with(timeout=10)
        assert policy.last_restart_at == NOW
        assert policy.restart_count_window == 1
        assert policy.window_started_at == NOW
        assert policy.unhealthy_streak == 0
        actions = _audit_actions(db_session)
        assert "CONTAINER_AUTO_RESTART" in actions

    def test_cooldown_prevents_restart(self, db_session: Session) -> None:
        policy = _make_policy(
            db_session,
            unhealthy_threshold=1,
            unhealthy_streak=5,
            restart_cooldown_seconds=300,
            last_restart_at=NOW - timedelta(seconds=5),
        )
        container = _container(policy.container_name, "unhealthy")

        with patch(
            "app.services.container_service._get_client",
            return_value=_client_for(container),
        ):
            stats = auto_heal_service.poll_once(db_session, now=NOW)

        assert stats["restarted"] == 0
        container.restart.assert_not_called()
        assert _audit_actions(db_session) == []

    def test_records_recovery_event(self, db_session: Session) -> None:
        policy = _make_policy(
            db_session,
            unhealthy_streak=2,
            last_health_status="unhealthy",
        )
        container = _container(policy.container_name, "healthy")

        with patch(
            "app.services.container_service._get_client",
            return_value=_client_for(container),
        ):
            stats = auto_heal_service.poll_once(db_session, now=NOW)

        assert stats["recovered"] == 1
        assert policy.unhealthy_streak == 0
        assert policy.last_health_status == "healthy"
        assert "CONTAINER_RECOVERED" in _audit_actions(db_session)

    def test_restart_failure_is_audited_and_counted(self, db_session: Session) -> None:
        policy = _make_policy(db_session, unhealthy_threshold=1, restart_cooldown_seconds=0)
        container = _container(policy.container_name, "unhealthy")
        container.restart.side_effect = RuntimeError("engine down")

        with patch(
            "app.services.container_service._get_client",
            return_value=_client_for(container),
        ):
            stats = auto_heal_service.poll_once(db_session, now=NOW)

        assert stats["restarted"] == 1
        log = db_session.execute(
            select(AuditLog).where(AuditLog.action == "CONTAINER_AUTO_RESTART")
        ).scalar_one()
        assert log.details is not None
        assert log.details["result"] == "failed"

    def test_ignores_disabled_policies(self, db_session: Session) -> None:
        _make_policy(db_session, auto_heal_enabled=False)
        client = _client_for(_container("x", "unhealthy"))

        with patch(
            "app.services.container_service._get_client", return_value=client
        ):
            stats = auto_heal_service.poll_once(db_session, now=NOW)

        assert stats["checked"] == 0
        client.containers.get.assert_not_called()

    def test_missing_container_is_skipped(self, db_session: Session) -> None:
        _make_policy(db_session)

        with patch(
            "app.services.container_service._get_client",
            return_value=_client_for(None, error=NotFound("gone")),
        ):
            stats = auto_heal_service.poll_once(db_session, now=NOW)

        assert stats["checked"] == 1
        assert stats["errors"] == 0

    def test_docker_unavailable_returns_error_stats(self, db_session: Session) -> None:
        _make_policy(db_session)

        with patch(
            "app.services.container_service._get_client",
            side_effect=RuntimeError("no docker"),
        ):
            stats = auto_heal_service.poll_once(db_session, now=NOW)

        assert stats["errors"] == 1


def _create_user(db: Session, *, role: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    username = f"heal_{suffix}"
    return auth_service.create_user(
        db, username, f"{username}@example.com", PASSWORD, role=role
    )


def _login(client: TestClient, username: str) -> str:
    response = client.post(
        "/auth/login", data={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["data"]["access_token"])


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestAutoHealApi:
    def test_list_requires_auth(self, client: TestClient) -> None:
        assert client.get("/container-policies").status_code == 401

    def test_list_policies_and_worker_status(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role="viewer")
        token = _login(client, user.username)
        policy = _make_policy(db_session)

        response = client.get("/container-policies", headers=_headers(token))

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        names = [item["container_name"] for item in data["items"]]
        assert policy.container_name in names
        assert data["worker"]["enabled"] is False
        assert data["worker"]["interval_seconds"] > 0

    def test_incidents_returns_only_auto_heal_events(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role="viewer")
        token = _login(client, user.username)
        name = f"auto-{uuid.uuid4().hex[:6]}"
        for action in ("CONTAINER_UNHEALTHY", "CONTAINER_AUTO_RESTART", "CONTAINER_DELETE"):
            audit_service.record(
                audit_service.AuditEvent(
                    action=action,
                    method="SYSTEM",
                    path=f"/containers/{name}",
                    status_code=200,
                    username="system",
                    resource_type="container",
                    resource_id=name,
                ),
                db=db_session,
            )
        db_session.flush()

        response = client.get(
            f"/container-policies/incidents?container_name={name}",
            headers=_headers(token),
        )

        assert response.status_code == 200, response.text
        items = response.json()["data"]
        assert [item["action"] for item in items] == [
            "CONTAINER_AUTO_RESTART",
            "CONTAINER_UNHEALTHY",
        ]
        assert all(item["container_name"] == name for item in items)

    def test_incidents_respects_limit(
        self, client: TestClient, db_session: Session
    ) -> None:
        user = _create_user(db_session, role="viewer")
        token = _login(client, user.username)
        name = f"auto-{uuid.uuid4().hex[:6]}"
        for _ in range(5):
            audit_service.record(
                audit_service.AuditEvent(
                    action="CONTAINER_UNHEALTHY",
                    method="SYSTEM",
                    path=f"/containers/{name}",
                    status_code=200,
                    username="system",
                    resource_type="container",
                    resource_id=name,
                ),
                db=db_session,
            )
        db_session.flush()

        response = client.get(
            f"/container-policies/incidents?container_name={name}&limit=2",
            headers=_headers(token),
        )

        assert response.status_code == 200, response.text
        assert len(response.json()["data"]) == 2
        total = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
        assert total >= 5
