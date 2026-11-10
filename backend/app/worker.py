"""
ARQ Worker Settings — konfigurasi worker untuk memproses deployment queue.

Jalankan worker dengan:
    arq app.worker.WorkerSettings

Worker akan:
  1. Connect ke Redis (settings.redis_dsn).
  2. Poll queue "arq:queue" untuk job.
  3. Execute run_deployment_background untuk setiap job.
  4. Handle max_jobs concurrent (settings.ARQ_MAX_JOBS).

Catatan: implementasi deployment saat ini menggunakan FastAPI BackgroundTasks
(berjalan in-process). WorkerSettings ini disiapkan untuk migrasi ke ARQ
(out-of-process worker) di masa depan jika dibutuhkan horizontal scaling.
"""

from __future__ import annotations

from loguru import logger

from app.config import settings
from app.services.deployment_queue import run_deployment_background

try:
    from arq.connections import RedisSettings
except ImportError:  # arq belum di-install — stub agar modul tetap importable
    RedisSettings = None  # type: ignore[assignment,misc]


class WorkerSettings:
    """
    Konfigurasi ARQ worker.

    Dokumentasi: https://arq-docs.helpmanual.io/
    """

    # Redis connection — ARQ butuh RedisSettings object, bukan plain dict.
    redis_settings = (
        RedisSettings(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=None,  # Tambahkan jika Redis butuh auth
            database=0,
        )
        if RedisSettings is not None
        else None
    )

    # Fungsi-fungsi yang bisa dipanggil worker
    functions = [run_deployment_background]

    # Konfigurasi worker
    max_jobs = settings.ARQ_MAX_JOBS
    job_timeout = settings.ARQ_JOB_TIMEOUT

    # Health check interval (detik)
    health_check_interval = 30

    # Maksimal retry per job sebelum dianggap gagal permanen
    max_tries = 5

    async def on_startup(self, ctx: dict) -> None:
        logger.info("ARQ worker started.")

    async def on_shutdown(self, ctx: dict) -> None:
        logger.info("ARQ worker shutting down.")

    async def on_job_done(self, ctx: dict) -> None:
        logger.info(f"ARQ job done: {ctx.get('job_id', 'unknown')}")
