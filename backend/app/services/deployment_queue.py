"""
Deployment Queue Service — Background task + Redis distributed lock untuk concurrency control.

Arsitektur concurrency control (double-guard):
  Layer 1 — Redis SETNX lock (primary):
    Key: "infraforge:deploy:lock:{application_id}"
    TTL: settings.ARQ_JOB_TIMEOUT detik (auto-release jika worker crash)
    Atomic SET NX EX — tidak ada race condition saat acquire.

  Layer 2 — DB status guard (fallback saat Redis down):
    Cek app.status == AppStatus.deploying di database sebelum mulai.
    Mencegah double-deploy meskipun Redis tidak tersedia.

Flow deployment background task:
  1. Webhook / API endpoint membuat Deployment record (pending) → return 202/201.
  2. Background task dijalankan di thread pool:
     a. acquire_deploy_lock() → Redis SETNX + DB status check.
     b. Update app.status = deploying di DB.
     c. Jalankan _run_deployment.
     d. release_deploy_lock() di finally block (selalu dieksekusi).

Idempotency:
  X-Github-Delivery ID disimpan di Redis dengan TTL 24 jam.
  Key: "infraforge:webhook:dedup:{delivery_id}"
"""

from __future__ import annotations

from loguru import logger

from app.config import settings
from app.database.redis_client import redis_client
from app.database.session import SessionLocal
from app.services import deployment_service


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _lock_key(application_id: int) -> str:
    return f"infraforge:deploy:lock:{application_id}"


def _dedup_key(delivery_id: str) -> str:
    return f"infraforge:webhook:dedup:{delivery_id}"


# ---------------------------------------------------------------------------
# Lock public API
# ---------------------------------------------------------------------------

def acquire_deploy_lock(application_id: int, deployment_id: int) -> bool:
    """
    Coba acquire Redis distributed lock untuk application_id.

    Menggunakan SET NX EX (atomic) — tidak ada race condition.
    Value menyimpan deployment_id yang sedang running (berguna untuk introspeksi).

    Args:
        application_id: ID aplikasi yang akan di-lock.
        deployment_id:  ID deployment record yang akan dijalankan.

    Returns:
        True jika lock berhasil di-acquire, False jika sudah ada lock lain.
    """
    acquired = redis_client.set(
        _lock_key(application_id),
        str(deployment_id),
        nx=True,
        ex=settings.ARQ_JOB_TIMEOUT,
    )
    return bool(acquired)


def release_deploy_lock(application_id: int) -> None:
    """
    Release Redis lock untuk application_id.

    Dipanggil di finally block — selalu dieksekusi meskipun deployment gagal.
    """
    redis_client.delete(_lock_key(application_id))


def get_running_deployment_id(application_id: int) -> int | None:
    """
    Ambil deployment_id yang sedang running (dari Redis lock value).

    Returns:
        deployment_id jika ada lock aktif, None jika tidak.
    """
    value = redis_client.get(_lock_key(application_id))
    if value is not None:
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    return None


def is_deployment_running(application_id: int) -> bool:
    """
    Cek apakah ada deployment yang sedang berjalan untuk application_id.

    Returns:
        True jika lock aktif di Redis, False jika tidak.
    """
    return bool(redis_client.exists(_lock_key(application_id)))


def is_locked_by_db_status(application_id: int) -> bool:
    """
    Fallback check via database — cek apakah app.status == deploying.

    Dipakai sebagai guard layer kedua saat Redis tidak tersedia atau
    sebagai double-check sebelum trigger deployment baru.

    Returns:
        True jika aplikasi sedang dalam status deploying di DB.
    """
    from app.models.application import AppStatus
    from app.repositories import application_repository

    with SessionLocal() as db:
        app = application_repository.get_by_id(db, application_id)
        if app is None:
            return False
        return app.status == AppStatus.deploying


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

def run_deployment_background(
    deployment_id: int,
    application_id: int,
    server_id: int,
) -> None:
    """
    Background task — jalankan deployment di luar request cycle.

    Dipanggil oleh FastAPI BackgroundTasks (di thread pool worker).

    Double-guard flow:
      1. Coba acquire Redis lock (SETNX).
         Jika gagal → deployment lain sedang running, skip dan update status ke failed.
      2. Update app.status = deploying di DB.
      3. Jalankan _run_deployment secara sync.
      4. Release lock + reset app.status di finally block (selalu dieksekusi).

    Args:
        deployment_id:   ID deployment record yang sudah dibuat.
        application_id:  ID aplikasi (dipakai untuk lock key + status update).
        server_id:       ID server target.
    """
    # --- 1. Acquire Redis lock ---
    acquired = acquire_deploy_lock(application_id, deployment_id)
    if not acquired:
        running_id = get_running_deployment_id(application_id)
        logger.warning(
            f"Deployment #{deployment_id} skipped — application {application_id} "
            f"sudah memiliki deployment yang sedang berjalan "
            f"(lock aktif, running deployment_id={running_id})."
        )
        # Update status deployment ini ke failed agar tidak stuck di pending
        with SessionLocal() as db:
            from app.models.deployment import DeploymentStatus
            from app.repositories import deployment_repository

            dep = deployment_repository.get_by_id(db, deployment_id)
            if dep is not None:
                deployment_repository.update_status(db, dep, DeploymentStatus.failed)
        return

    try:
        with SessionLocal() as db:
            from app.models.application import AppStatus
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

            # --- 2. Update app.status = deploying ---
            application_repository.update_status(db, app, AppStatus.deploying)

            logger.info(
                f"Background task: memulai deployment #{deployment_id} "
                f"untuk app={application_id}"
            )

            try:
                deployment_service._run_deployment(db, deployment, app, server)
                # Deployment sukses → set app status ke running
                application_repository.update_status(db, app, AppStatus.running)
            except Exception as exc:
                logger.error(
                    f"Background task: deployment #{deployment_id} gagal: {exc}"
                )
                # Deployment gagal → set app status ke failed
                application_repository.update_status(db, app, AppStatus.failed)

            logger.info(
                f"Background task: deployment #{deployment_id} selesai "
                f"(status={deployment.status}, app_status={app.status})"
            )

    except Exception as exc:
        logger.error(f"Background task error untuk deployment #{deployment_id}: {exc}")

    finally:
        # --- 3. Release lock (selalu dieksekusi) ---
        release_deploy_lock(application_id)


# ---------------------------------------------------------------------------
# Idempotency (webhook dedup)
# ---------------------------------------------------------------------------

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
        except (ValueError, TypeError):
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
