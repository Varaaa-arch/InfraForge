"""
Health Check Service — Task 3.8.

Setelah `docker compose up` selesai, container perlu beberapa detik untuk
benar-benar siap. Modul ini menyediakan:

  verify_deployment_health(compose_project, startup_delay, retries)
    → Tunggu startup_delay detik, lalu periksa status semua container
      dalam compose project tersebut menggunakan Docker SDK.
    → Kembalikan HealthCheckResult.

  run_health_check(compose_project, startup_delay, retries)
    → Sync wrapper — menjalankan coroutine di event-loop baru menggunakan
      asyncio.run(), sehingga bisa dipanggil dari kode synchronous di
      deployment_service.

Status container yang dianggap HEALTHY:
  "running"  — container aktif berjalan
  "healthy"  — container punya healthcheck dan reported healthy

Status yang dianggap UNHEALTHY:
  "exited"       — container berhenti (crash atau selesai)
  "restarting"   — container sedang restart loop
  "dead"         — container killed
  "paused"       — container paused (tidak diharapkan)
  Tidak ada container ditemukan → UNHEALTHY

Desain:
- Semua I/O Docker di-mock saat unit test (tidak ada Docker daemon nyata).
- asyncio.sleep juga di-mock sehingga test berjalan instan.
- compose_project dipakai sebagai label filter Docker (label
  "com.docker.compose.project" yang di-set otomatis oleh docker compose).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from loguru import logger

# Status yang dianggap sehat
_HEALTHY_STATUSES: frozenset[str] = frozenset({"running", "healthy"})
# Status yang dianggap tidak sehat
_UNHEALTHY_STATUSES: frozenset[str] = frozenset({"exited", "restarting", "dead", "paused"})


@dataclass
class HealthCheckResult:
    """Hasil pengecekan health setelah deployment."""

    healthy: bool
    containers_checked: int
    statuses: dict[str, str] = field(default_factory=dict)
    """Mapping nama_container → status."""
    message: str = ""


def _check_compose_containers(compose_project: str) -> HealthCheckResult:
    """
    Periksa status semua container dalam docker compose project.

    Menggunakan label filter `com.docker.compose.project=<project_name>`
    yang secara otomatis di-set oleh `docker compose up`.

    Returns:
        HealthCheckResult
    """
    try:
        import docker
        import docker.errors
    except ImportError as exc:
        raise ImportError("docker-py diperlukan untuk health check.") from exc

    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:
        raise RuntimeError(f"Tidak dapat terhubung ke Docker daemon: {exc}") from exc

    try:
        containers = client.containers.list(
            all=True,
            filters={"label": f"com.docker.compose.project={compose_project}"},
        )
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil container list: {exc}") from exc

    if not containers:
        return HealthCheckResult(
            healthy=False,
            containers_checked=0,
            message=(
                f"Tidak ada container ditemukan untuk compose project '{compose_project}'. "
                "Pastikan nama project benar atau compose up berhasil."
            ),
        )

    statuses: dict[str, str] = {}
    all_healthy = True

    for c in containers:
        # Health status dari docker inspect (jika ada healthcheck)
        health = c.attrs.get("State", {}).get("Health", {})
        health_status = health.get("Status", "") if health else ""

        raw_status: str = c.status  # running, exited, paused, dll

        # Tentukan efektif status: prefer health_status jika tersedia
        effective = health_status if health_status else raw_status
        statuses[c.name] = effective

        if effective not in _HEALTHY_STATUSES:
            all_healthy = False
            logger.warning(
                f"Container '{c.name}' tidak sehat: status={effective}"
            )

    if all_healthy:
        msg = (
            f"Semua {len(containers)} container dalam kondisi sehat "
            f"(project='{compose_project}')."
        )
    else:
        unhealthy = [n for n, s in statuses.items() if s not in _HEALTHY_STATUSES]
        msg = (
            f"{len(unhealthy)} dari {len(containers)} container tidak sehat: "
            f"{', '.join(unhealthy)}"
        )

    return HealthCheckResult(
        healthy=all_healthy,
        containers_checked=len(containers),
        statuses=statuses,
        message=msg,
    )


async def verify_deployment_health(
    compose_project: str,
    startup_delay: float = 8.0,
    retries: int = 3,
    retry_interval: float = 3.0,
) -> HealthCheckResult:
    """
    Async core: tunggu startup, lalu cek health container dengan retry.

    Args:
        compose_project: Nama project docker compose (digunakan sebagai label filter).
        startup_delay:   Detik menunggu setelah compose up sebelum pengecekan pertama.
        retries:         Jumlah percobaan pengecekan ulang jika hasilnya unhealthy.
        retry_interval:  Detik antara setiap percobaan ulang.

    Returns:
        HealthCheckResult dari percobaan terakhir.
    """
    logger.info(
        f"Health check: menunggu {startup_delay}s startup "
        f"(project='{compose_project}') ..."
    )
    await asyncio.sleep(startup_delay)

    result = HealthCheckResult(healthy=False, containers_checked=0)

    for attempt in range(1, retries + 1):
        logger.info(f"Health check attempt {attempt}/{retries} ...")
        try:
            result = _check_compose_containers(compose_project)
        except RuntimeError as exc:
            result = HealthCheckResult(
                healthy=False,
                containers_checked=0,
                message=str(exc),
            )

        if result.healthy:
            logger.info(f"Health check PASSED pada attempt {attempt}: {result.message}")
            return result

        logger.warning(
            f"Health check attempt {attempt} FAILED: {result.message}"
        )
        if attempt < retries:
            await asyncio.sleep(retry_interval)

    logger.error(f"Health check FAILED setelah {retries} percobaan.")
    return result


def run_health_check(
    compose_project: str,
    startup_delay: float = 8.0,
    retries: int = 3,
    retry_interval: float = 3.0,
) -> HealthCheckResult:
    """
    Sync wrapper untuk verify_deployment_health.

    Menjalankan coroutine di asyncio event-loop baru sehingga bisa
    dipanggil dari kode synchronous (deployment_service._run_deployment).
    """
    return asyncio.run(
        verify_deployment_health(
            compose_project=compose_project,
            startup_delay=startup_delay,
            retries=retries,
            retry_interval=retry_interval,
        )
    )
