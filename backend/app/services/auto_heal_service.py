"""Auto-healing container: health polling, restart, dan audit insiden.

Worker berjalan sebagai asyncio task di lifespan FastAPI. Setiap
``HEALTH_POLL_INTERVAL_SECONDS`` worker membaca status health container yang
memiliki policy ``auto_heal_enabled``, mencatat insiden ke audit log, dan
me-restart container setelah ``unhealthy_threshold`` cek gagal berturut-turut
dengan batas ``max_restarts`` per window dan ``restart_cooldown_seconds``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.database.session import SessionLocal
from app.models.container_policy import ContainerPolicy
from app.repositories import container_policy_repository
from app.services import audit_service, container_service

DecisionAction = Literal["noop", "record_unhealthy", "restart", "record_recovered"]

DECISION_NOOP: DecisionAction = "noop"
DECISION_RECORD_UNHEALTHY: DecisionAction = "record_unhealthy"
DECISION_RESTART: DecisionAction = "restart"
DECISION_RECORD_RECOVERED: DecisionAction = "record_recovered"

INCIDENT_ACTIONS = (
    "CONTAINER_UNHEALTHY",
    "CONTAINER_AUTO_RESTART",
    "CONTAINER_RECOVERED",
)

_worker_state: dict[str, Any] = {
    "running": False,
    "last_poll_at": None,
    "last_error": None,
    "last_stats": None,
}
_worker_task: asyncio.Task[None] | None = None
_stop_event: asyncio.Event | None = None


@dataclass(frozen=True)
class HealthSnapshot:
    status: str
    health: str | None


@dataclass(frozen=True)
class AutoHealDecision:
    action: DecisionAction
    reason: str
    streak: int = 0
    restarts_in_window: int = 0


@dataclass
class PollStats:
    checked: int = 0
    unhealthy: int = 0
    restarted: int = 0
    recovered: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "checked": self.checked,
            "unhealthy": self.unhealthy,
            "restarted": self.restarted,
            "recovered": self.recovered,
            "errors": self.errors,
        }


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _window_active(
    policy: ContainerPolicy, now: datetime, window_minutes: int
) -> bool:
    started = _as_aware_utc(policy.window_started_at)
    if started is None:
        return False
    return now - started <= timedelta(minutes=window_minutes)


def _cooldown_active(policy: ContainerPolicy, now: datetime) -> bool:
    last = _as_aware_utc(policy.last_restart_at)
    if last is None:
        return False
    cooldown = (
        settings.AUTO_HEAL_COOLDOWN_SECONDS
        if policy.restart_cooldown_seconds is None
        else policy.restart_cooldown_seconds
    )
    return (now - last).total_seconds() < int(cooldown)


def decide_action(
    policy: ContainerPolicy,
    snapshot: HealthSnapshot,
    *,
    now: datetime | None = None,
    window_minutes: int | None = None,
) -> AutoHealDecision:
    """Tentukan aksi auto-healing tanpa efek samping (pure function)."""
    now = now or datetime.now(tz=UTC)
    window_minutes = (
        settings.AUTO_HEAL_WINDOW_MINUTES if window_minutes is None else window_minutes
    )
    health = (snapshot.health or "").lower()

    if health == "unhealthy":
        if _cooldown_active(policy, now):
            return AutoHealDecision(DECISION_NOOP, "cooldown aktif")

        max_restarts = int(
            settings.AUTO_HEAL_MAX_RESTARTS
            if policy.max_restarts is None
            else policy.max_restarts
        )
        threshold = max(
            1,
            int(
                settings.HEALTH_UNHEALTHY_THRESHOLD
                if policy.unhealthy_threshold is None
                else policy.unhealthy_threshold
            ),
        )
        in_window = _window_active(policy, now, window_minutes)
        restarts = int(policy.restart_count_window or 0) if in_window else 0
        if restarts >= max_restarts:
            return AutoHealDecision(
                DECISION_NOOP,
                f"batas restart tercapai ({restarts}/{max_restarts})",
                restarts_in_window=restarts,
            )

        streak = int(policy.unhealthy_streak or 0) + 1
        if streak >= threshold:
            return AutoHealDecision(
                DECISION_RESTART,
                f"{streak} cek unhealthy berturut-turut",
                streak=streak,
                restarts_in_window=restarts,
            )
        return AutoHealDecision(
            DECISION_RECORD_UNHEALTHY,
            f"streak {streak}/{threshold}",
            streak=streak,
            restarts_in_window=restarts,
        )

    if health == "healthy" and (
        int(policy.unhealthy_streak or 0) > 0
        or (policy.last_health_status or "").lower() in {"unhealthy", "starting"}
    ):
        return AutoHealDecision(DECISION_RECORD_RECOVERED, "container sehat kembali")

    return AutoHealDecision(DECISION_NOOP, "tidak perlu tindakan")


def _audit(
    db: Session,
    action: str,
    policy: ContainerPolicy,
    *,
    details: dict[str, Any],
) -> None:
    audit_service.record(
        audit_service.AuditEvent(
            action=action,
            method="SYSTEM",
            path=f"/containers/{policy.container_name}",
            status_code=200,
            username="system",
            resource_type="container",
            resource_id=policy.container_name,
            details=details,
        ),
        db=db,
    )


def apply_decision(
    db: Session,
    policy: ContainerPolicy,
    snapshot: HealthSnapshot,
    decision: AutoHealDecision,
    *,
    container: Any,
    now: datetime | None = None,
    window_minutes: int | None = None,
) -> None:
    """Terapkan keputusan ke policy, Docker, dan audit log (belum commit)."""
    now = now or datetime.now(tz=UTC)
    window_minutes = (
        settings.AUTO_HEAL_WINDOW_MINUTES if window_minutes is None else window_minutes
    )
    previous_health = policy.last_health_status
    policy.last_health_status = snapshot.health

    if decision.action == DECISION_RECORD_UNHEALTHY:
        policy.unhealthy_streak = decision.streak
        _audit(
            db,
            "CONTAINER_UNHEALTHY",
            policy,
            details={
                "health": snapshot.health,
                "status": snapshot.status,
                "streak": decision.streak,
                "threshold": policy.unhealthy_threshold,
            },
        )
        return

    if decision.action == DECISION_RESTART:
        if not _window_active(policy, now, window_minutes):
            policy.window_started_at = now
            policy.restart_count_window = 0
        policy.unhealthy_streak = 0
        policy.last_restart_at = now
        policy.restart_count_window = int(policy.restart_count_window or 0) + 1

        result = "success"
        try:
            container.restart(timeout=10)
        except Exception as exc:  # noqa: BLE001 — infrastruktur eksternal
            result = "failed"
            policy.last_health_status = previous_health
            logger.warning(
                f"Auto-restart {policy.container_name} gagal: {exc}"
            )

        _audit(
            db,
            "CONTAINER_AUTO_RESTART",
            policy,
            details={
                "result": result,
                "health": snapshot.health,
                "streak": decision.streak,
                "restart_count_window": policy.restart_count_window,
                "max_restarts": policy.max_restarts,
                "reason": decision.reason,
            },
        )
        return

    if decision.action == DECISION_RECORD_RECOVERED:
        policy.unhealthy_streak = 0
        _audit(
            db,
            "CONTAINER_RECOVERED",
            policy,
            details={
                "health": snapshot.health,
                "previous_health": previous_health,
            },
        )


def _poll_with_session() -> dict[str, int]:
    with SessionLocal() as db:
        return poll_once(db)


def poll_once(
    db: Session,
    *,
    now: datetime | None = None,
    window_minutes: int | None = None,
) -> dict[str, int]:
    """Satu siklus polling untuk semua policy auto-healing yang aktif."""
    now = now or datetime.now(tz=UTC)
    stats = PollStats()
    policies = container_policy_repository.list_auto_heal_enabled(db)
    if not policies:
        return stats.as_dict()

    try:
        client = container_service._get_client()
    except Exception as exc:  # noqa: BLE001
        stats.errors += 1
        _worker_state["last_error"] = str(exc)
        logger.warning(f"Auto-heal: Docker tidak tersedia: {exc}")
        return stats.as_dict()

    try:
        from docker.errors import NotFound
    except ImportError:  # pragma: no cover - docker wajib terpasang
        NotFound = ()  # type: ignore[assignment,misc]

    for policy in policies:
        stats.checked += 1
        try:
            container = client.containers.get(policy.container_name)
        except NotFound:
            continue
        except Exception as exc:  # noqa: BLE001
            stats.errors += 1
            _worker_state["last_error"] = str(exc)
            logger.warning(
                f"Auto-heal: gagal mengambil container "
                f"{policy.container_name}: {exc}"
            )
            continue

        try:
            attrs = container_service._safe_attrs(container)
            snapshot = HealthSnapshot(
                status=str(getattr(container, "status", "") or ""),
                health=container_service._extract_health(attrs),
            )
            decision = decide_action(
                policy, snapshot, now=now, window_minutes=window_minutes
            )
            if decision.action == DECISION_NOOP:
                if policy.last_health_status != snapshot.health:
                    policy.last_health_status = snapshot.health
                continue

            apply_decision(
                db,
                policy,
                snapshot,
                decision,
                container=container,
                now=now,
                window_minutes=window_minutes,
            )
            db.commit()
            if decision.action == DECISION_RECORD_UNHEALTHY:
                stats.unhealthy += 1
            elif decision.action == DECISION_RESTART:
                stats.restarted += 1
            elif decision.action == DECISION_RECORD_RECOVERED:
                stats.recovered += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            stats.errors += 1
            _worker_state["last_error"] = str(exc)
            logger.warning(
                f"Auto-heal: gagal memproses {policy.container_name}: {exc}"
            )

    return stats.as_dict()


def get_worker_status() -> dict[str, Any]:
    """Status worker untuk endpoint API."""
    return {
        "enabled": bool(settings.AUTO_HEAL_ENABLED),
        "running": bool(_worker_state["running"]),
        "interval_seconds": settings.HEALTH_POLL_INTERVAL_SECONDS,
        "unhealthy_threshold_default": settings.HEALTH_UNHEALTHY_THRESHOLD,
        "max_restarts_default": settings.AUTO_HEAL_MAX_RESTARTS,
        "last_poll_at": _worker_state["last_poll_at"],
        "last_error": _worker_state["last_error"],
        "last_stats": _worker_state["last_stats"],
    }


async def _poll_loop(stop_event: asyncio.Event) -> None:
    _worker_state["running"] = True
    logger.info(
        f"Auto-heal worker aktif (interval={settings.HEALTH_POLL_INTERVAL_SECONDS}s)"
    )
    try:
        while not stop_event.is_set():
            try:
                _worker_state["last_stats"] = await asyncio.to_thread(_poll_with_session)
                _worker_state["last_poll_at"] = datetime.now(tz=UTC)
                _worker_state["last_error"] = None
            except Exception as exc:  # noqa: BLE001 — loop tidak boleh mati
                _worker_state["last_error"] = str(exc)
                logger.warning(f"Auto-heal poll gagal: {exc}")

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=max(5, settings.HEALTH_POLL_INTERVAL_SECONDS),
                )
            except TimeoutError:
                continue
    finally:
        _worker_state["running"] = False
        logger.info("Auto-heal worker berhenti")


def start_worker() -> None:
    """Jalankan worker di event loop aktif (dipanggil dari lifespan)."""
    global _worker_task, _stop_event
    if not settings.AUTO_HEAL_ENABLED or _worker_task is not None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - tidak ada loop aktif
        logger.warning("Auto-heal worker tidak dimulai: event loop tidak aktif")
        return
    _stop_event = asyncio.Event()
    _worker_task = loop.create_task(_poll_loop(_stop_event))


async def stop_worker() -> None:
    """Berhenti dan tunggu task worker selesai."""
    global _worker_task, _stop_event
    task, stop_event = _worker_task, _stop_event
    _worker_task = None
    _stop_event = None
    if task is None:
        return
    if stop_event is not None:
        stop_event.set()
    try:
        await asyncio.wait_for(task, timeout=10)
    except TimeoutError:  # pragma: no cover - shutdown defensif
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
