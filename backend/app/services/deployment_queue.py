"""
Deployment Queue Service — Background task + Redis lock untuk race condition prevention.

Menggunakan FastAPI BackgroundTasks + Redis SETNX lock:
  1. Webhook endpoint membuat Deployment record (sync) → return 202 ke GitHub.
  2. Webhook endpoint men-enqueue background task via FastAPI BackgroundTasks.
  3. Background task dijalankan di thread pool:
     a. Acquire Redis lock per application_id (SETNX) → mencegah concurrent deploy.
     b. Panggil _run_deployment (sync, blocking) di thread pool.
     c. Release lock di finally block.

Redis lock key format:
    "infraforge:deploy:lock:{application_id}"
    TTL: settings.ARQ_JOB_TIMEOUT detik (auto-release jika worker crash)

Idempotency:
    X-Github-Delivery ID disimpan di Redis dengan TTL 24 jam.
    Jika delivery ID sudah ada → skip (return existing deployment_id).
    Key: "infraforge:webhook:dedup:{delivery_id}"
"""

from __future__ import annotations

from loguru import logger

from app.config import settings
from app.database.redis_client import redis_client
from app.database.session import SessionLocal
from app.services import deployment_service


def _lock_key(application_id: int) -> str:
    return f"infraforge:deploy:lock:{application_id}"


def _dedup_key(delivery_id: str) -> str:
    return f"infraforge:webhook:dedup:{delivery_id}"


def run_deployment_background(
    deployment_id: int,
    application_id: int,
    server_id: int,
) -> None:
    """
    Background task — jalankan deployment di luar request cycle.

    Dipanggil oleh FastAPI BackgroundTasks (di thread pool worker).

    Flow:
      1. Acquire Redis lock per application_id (SETNX + TTL).
      2. Jika lock gagal (deployment lain sedang berjalan) → skip.
      3. Jalankan _run_deployment secara sync.
      4. Release lock di finally block.

    Args:
        deployment_id:   ID deployment record yang sudah dibuat.
        application_id:  ID aplikasi (dipakai untuk lock key).
        server_id:       ID server target.
    """
    lock_key = _lock_key(application_id)
    lock_ttl = settings.ARQ_JOB_TIMEOUT

    # --- 1. Acquire Redis lock (SETNX) ---
    acquired = redis_client.set(lock_key, str(deployment_id), nx=True, ex=lock_ttl)
    if not acquired:
        logger.warning(
            f"Deployment #{deployment_id} skipped — application {application_id} "
            f"sudah memiliki deployment yang sedang berjalan (lock: {lock_key})."
        )
        return

    try:
        # --- 2. Jalankan deployment ---
        db = SessionLocal()
        try:
            from app.models.deployment import DeploymentStatus
            from app.repositories import (
                application_repository,
                deployment_repository,
                server_repository,
            )

            deployment = deployment_repository.get_by_id(db, deployment_id)
            if deployment is None:
                logger.error(f"Deployment #{deployment_id} tidak ditemukan di DB.")
                return

            app = application_repository.get_by_id(db, application_id)
            server = server_repository.get_by_id(db, server_id)

            if app is None or server is None:
                logger.error(
                    f"Application {application_id} atau server {server_id} tidak ditemukan."
                )
                deployment_repository.update_status(db, deployment, DeploymentStatus.failed)
                return

            logger.info(
                f"Background task: memulai deployment #{deployment_id} "
                f"untuk app={application_id}"
            )

            deployment_service._run_deployment(db, deployment, app, server)

            logger.info(
                f"Background task: deployment #{deployment_id} selesai "
                f"(status={deployment.status})"
            )
        finally:
            db.close()

    except Exception as exc:
        logger.error(f"Background task error untuk deployment #{deployment_id}: {exc}")

    finally:
        # --- 3. Release lock ---
        redis_client.delete(lock_key)


def is_duplicate_delivery(delivery_id: str) -> int | None:
    """
    Cek apakah webhook delivery ID sudah pernah diproses (idempotency).

    Returns:
        Existing deployment_id jika sudah pernah diproses, None jika baru.
    """
    if not delivery_id:
        return None
    existing = redis_client.get(_dedup_key(delivery_id))
    if existing is not None:
        try:
            return int(existing)
        except ValueError:
            return None
    return None


def mark_delivery_processed(delivery_id: str, deployment_id: int) -> None:
    """Simpan delivery ID ke Redis untuk dedup (TTL 24 jam)."""
    if delivery_id:
        redis_client.setex(
            _dedup_key(delivery_id),
            settings.ARQ_DELIVERY_TTL,
            str(deployment_id),
        )


def is_deployment_running(application_id: int) -> bool:
    """
    Cek apakah ada deployment yang sedang berjalan untuk application_id tertentu.

    Returns:
        True jika lock key ada di Redis, False jika tidak.
    """
    return bool(redis_client.exists(_lock_key(application_id)))
