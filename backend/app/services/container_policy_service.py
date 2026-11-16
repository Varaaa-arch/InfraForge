"""Service policy resource container: limit CPU/memory & restart policy.

Limit diterapkan langsung ke container running memakai Docker Engine API
``POST /containers/{id}/update``. Nilai policy disimpan agar bisa diterapkan
ulang saat container di-start/restart atau setelah ``docker compose up``
 membuat ulang container.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.container_policy import ContainerPolicy
from app.repositories import container_policy_repository
from app.schemas.container_policy import (
    CPU_PERIOD_DEFAULT,
    ContainerPolicyUpsert,
    EffectiveContainerLimits,
)
from app.services import container_service

RESTART_POLICIES = frozenset({"no", "always", "unless-stopped", "on-failure"})


def _restart_policy_dict(name: str) -> dict[str, Any]:
    policy = name if name in RESTART_POLICIES else "no"
    return {"Name": policy, "MaximumRetryCount": 0}


def get_effective_limits(attrs: dict[str, Any]) -> EffectiveContainerLimits:
    """Baca limit efektif dari ``HostConfig`` hasil inspect container."""
    host = attrs.get("HostConfig") or {}
    if not isinstance(host, dict):
        host = {}

    nano_cpus = int(host.get("NanoCpus") or 0)
    cpu_quota = int(host.get("CpuQuota") or 0)
    cpu_period = int(host.get("CpuPeriod") or 0)
    memory = int(host.get("Memory") or 0)
    restart = host.get("RestartPolicy") or {}
    restart_name = str(restart.get("Name") or "no") if isinstance(restart, dict) else "no"

    if nano_cpus:
        cores: float | None = round(nano_cpus / 1_000_000_000, 3)
    elif cpu_quota and cpu_period:
        cores = round(cpu_quota / cpu_period, 3)
    else:
        cores = None

    return EffectiveContainerLimits(
        cpu_limit_cores=cores,
        cpu_quota=cpu_quota or None,
        cpu_period=cpu_period or None,
        memory_limit_bytes=memory or None,
        restart_policy=restart_name or "no",
    )


def build_update_data(policy: ContainerPolicy) -> dict[str, Any]:
    """Bangun body Engine API ``POST /containers/{id}/update``.

    Nilai 0 dipakai untuk menghapus limit (unlimited). docker-py
    ``container.update()`` mengabaikan nilai 0 karena memakai pengecekan
    truthy, sehingga service ini memanggil Engine API secara langsung.
    """
    data: dict[str, Any] = {
        "CpuPeriod": int(policy.cpu_period or CPU_PERIOD_DEFAULT),
        "CpuQuota": int(policy.cpu_quota or 0),
        "Memory": int(policy.memory_limit_bytes or 0),
        "RestartPolicy": _restart_policy_dict(policy.restart_policy),
    }
    return data


def _update_container(container: Any, data: dict[str, Any]) -> None:
    client = getattr(container, "client", None)
    api = getattr(client, "api", None)
    if api is None or not hasattr(api, "_post_json"):
        # Fallback untuk objek yang tidak lengkap (mis. stub): gunakan API publik
        # docker-py. Limit 0 tidak bisa dikirim lewat jalur ini.
        kwargs: dict[str, Any] = {
            "restart_policy": data["RestartPolicy"],
        }
        if data.get("CpuQuota"):
            kwargs["cpu_quota"] = data["CpuQuota"]
        if data.get("CpuPeriod"):
            kwargs["cpu_period"] = data["CpuPeriod"]
        if data.get("Memory"):
            kwargs["mem_limit"] = data["Memory"]
        container.update(**kwargs)
        return

    url = api._url(f"/containers/{container.id}/update")
    api._post_json(url, data=data)


def apply_policy(policy: ContainerPolicy, container: Any | None = None) -> None:
    """Terapkan limit & restart policy ke container Docker."""
    if container is None:
        client = container_service._get_client()
        container = container_service._get_container(
            client, policy.container_id or policy.container_name
        )

    data = build_update_data(policy)
    try:
        _update_container(container, data)
    except Exception as exc:
        raise RuntimeError(
            f"Gagal menerapkan limit ke container {policy.container_name}: {exc}"
        ) from exc

    policy.applied_at = datetime.now(tz=UTC)
    policy.container_id = str(getattr(container, "id", policy.container_id) or "")
    logger.info(
        f"Policy resource diterapkan ke {policy.container_name}: "
        f"quota={data['CpuQuota']} period={data['CpuPeriod']} "
        f"memory={data['Memory']} restart={policy.restart_policy}"
    )


def _fetch_container_meta(container_id: str) -> tuple[Any, dict[str, Any]]:
    client = container_service._get_client()
    container = container_service._get_container(client, container_id)
    return container, container_service._safe_attrs(container)


def _container_name(container: Any, attrs: dict[str, Any], fallback: str) -> str:
    raw_name = attrs.get("Name")
    if isinstance(raw_name, str) and raw_name:
        return raw_name.lstrip("/")
    name = getattr(container, "name", None)
    return str(name) if name else fallback


def upsert_policy(
    db: Session,
    container_id: str,
    payload: ContainerPolicyUpsert,
) -> tuple[ContainerPolicy, EffectiveContainerLimits]:
    """Simpan policy lalu (opsional) terapkan langsung ke container."""
    container, attrs = _fetch_container_meta(container_id)
    name = _container_name(container, attrs, container_id)
    compose_project, compose_service = container_service._extract_compose_labels(attrs)

    policy = container_policy_repository.get_by_name(db, name)
    if policy is None:
        policy = container_policy_repository.create(
            db,
            container_name=name,
            container_id=str(getattr(container, "id", container_id)),
            compose_project=compose_project,
            compose_service=compose_service,
        )

    policy.container_id = str(getattr(container, "id", container_id))
    policy.compose_project = compose_project
    policy.compose_service = compose_service
    policy.cpu_limit_cores = payload.cpu_limit_cores
    policy.cpu_quota = payload.cpu_quota
    policy.cpu_period = payload.cpu_period or CPU_PERIOD_DEFAULT
    policy.memory_limit_bytes = (
        payload.memory_limit_mib * 1024 * 1024
        if payload.memory_limit_mib
        else None
    )
    policy.restart_policy = payload.restart_policy
    policy.auto_heal_enabled = payload.auto_heal_enabled
    policy.unhealthy_threshold = payload.unhealthy_threshold
    policy.max_restarts = payload.max_restarts
    policy.restart_cooldown_seconds = payload.restart_cooldown_seconds

    db.commit()
    db.refresh(policy)

    if payload.apply_now:
        apply_policy(policy, container=container)
        db.commit()
        db.refresh(policy)

    effective = get_effective_limits(container_service._safe_attrs(container))
    return policy, effective


def delete_policy(
    db: Session,
    container_id: str,
    *,
    reset_limits: bool = False,
) -> str:
    """Hapus policy. Jika ``reset_limits`` benar, hapus limit di Docker."""
    container, attrs = _fetch_container_meta(container_id)
    name = _container_name(container, attrs, container_id)
    policy = container_policy_repository.get_by_name(db, name)
    if policy is None:
        raise ValueError(f"Policy untuk container {name} tidak ditemukan")

    if reset_limits:
        reset = ContainerPolicy(
            container_name=name,
            cpu_period=CPU_PERIOD_DEFAULT,
            restart_policy=policy.restart_policy or "no",
        )
        try:
            _update_container(container, build_update_data(reset))
        except Exception as exc:
            raise RuntimeError(
                f"Gagal mereset limit container {name}: {exc}"
            ) from exc

    container_policy_repository.delete(db, policy)
    db.commit()
    return name


def get_policy_for_container(
    db: Session, container_id: str
) -> tuple[Any, dict[str, Any], str, ContainerPolicy | None]:
    container, attrs = _fetch_container_meta(container_id)
    name = _container_name(container, attrs, container_id)
    return container, attrs, name, container_policy_repository.get_by_name(db, name)


def reapply_for_container(container_name: str) -> bool:
    """Terapkan ulang policy setelah container start/restart. Best-effort."""
    try:
        with SessionLocal() as db:
            policy = container_policy_repository.get_by_name(db, container_name)
            if policy is None:
                return False
            apply_policy(policy)
            db.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — jangan gagalkan lifecycle container
        logger.warning(f"Gagal reapply policy untuk {container_name}: {exc}")
        return False


def reapply_all() -> int:
    """Terapkan ulang semua policy yang tersimpan. Best-effort."""
    applied = 0
    try:
        with SessionLocal() as db:
            policies = container_policy_repository.list_all(db)
            for policy in policies:
                try:
                    apply_policy(policy)
                    applied += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        f"Gagal reapply policy {policy.container_name}: {exc}"
                    )
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Gagal reapply policy container: {exc}")
    return applied
