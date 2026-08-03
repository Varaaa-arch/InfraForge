"""
Deployment Service — orkestrasi alur deployment (Task 3.6 + Task 3.8).

Alur eksekusi `_run_deployment`:
  1. Set status → deploying.
  2. Validasi konfigurasi (repository URL wajib ada).
  3. Clone repository via git_service (ke tmp/).
  4. Inject env vars dari DB ke .env di direktori clone.
  5. Jalankan docker compose build + up -d.
  6. Panggil run_health_check → cek status container setelah startup.
  7. Jika healthy → set status success.
     Jika unhealthy → raise RuntimeError → set status failed.
  8. Jika ada Exception → set status failed, re-raise.
  9. Cleanup tmp/ di finally block.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.server import Server
from app.repositories import application_repository
from app.repositories import deployment_repository
from app.repositories import env_var_repository
from app.repositories import server_repository
from app.services import encryption_service
from app.services import git_service
from app.services import health_check as health_check_service


# ---------------------------------------------------------------------------
# Internal helpers (dipisah agar bisa di-mock di unit test)
# ---------------------------------------------------------------------------

def _write_env_file(repo_dir: Path, env_vars: dict[str, str]) -> Path:
    """
    Tulis dictionary key=value ke file `.env` di dalam `repo_dir`.
    Return path file .env yang dibuat.
    """
    env_file = repo_dir / ".env"
    lines = [f"{k}={v}\n" for k, v in env_vars.items()]
    env_file.write_text("".join(lines), encoding="utf-8")
    logger.debug(f"Wrote {len(env_vars)} env vars to {env_file}")
    return env_file


def _run_compose(repo_dir: Path, compose_file: str) -> tuple[str, str]:
    """
    Jalankan `docker compose -f <compose_file> build` lalu
    `docker compose -f <compose_file> up -d` via subprocess.

    Returns:
        Tuple (stdout_build + stdout_up, stderr_build + stderr_up).

    Raises:
        RuntimeError jika salah satu perintah exit non-zero.
    """
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []

    for args in [
        ["docker", "compose", "-f", compose_file, "build", "--no-cache"],
        ["docker", "compose", "-f", compose_file, "up", "-d"],
    ]:
        logger.info(f"Running: {' '.join(args)} in {repo_dir}")
        result = subprocess.run(
            args,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=600,  # 10 menit per perintah
        )
        stdout_parts.append(result.stdout)
        stderr_parts.append(result.stderr)

        if result.returncode != 0:
            raise RuntimeError(
                f"Command '{' '.join(args)}' gagal (exit {result.returncode}):\n"
                f"{result.stderr}"
            )

    return "\n".join(stdout_parts), "\n".join(stderr_parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def trigger_deployment(
    db: Session,
    application_id: int,
    server_id: int,
    branch_override: str | None = None,
) -> Deployment:
    """
    Trigger deployment baru.

    1. Validasi aplikasi dan server ada di DB.
    2. Buat record Deployment awal (status=pending).
    3. Jalankan orkestrasi via run_deployment.

    Raises:
        ValueError: Jika aplikasi atau server tidak ditemukan.
    """
    app = application_repository.get_by_id(db, application_id)
    if app is None:
        raise ValueError(f"Application tidak ditemukan: {application_id}")

    server = server_repository.get_by_id(db, server_id)
    if server is None:
        raise ValueError(f"Server tidak ditemukan: {server_id}")

    branch = branch_override or app.branch
    deployment = deployment_repository.create(db, application_id, server_id, branch)

    try:
        _run_deployment(db, deployment, app, server)
    except Exception:
        # Status sudah diupdate di dalam _run_deployment pada blok except-nya.
        # Di sini hanya log dan re-raise agar caller juga tahu.
        logger.error(
            f"Deployment #{deployment.id} untuk app={application_id} gagal."
        )
        raise

    return deployment


def _run_deployment(
    db: Session,
    deployment: Deployment,
    app: Application,
    server: Server,  # noqa: ARG001  — akan dipakai saat remote SSH deployment
) -> None:
    """
    Orkestrasi deployment sebenarnya. Memodifikasi `deployment` di DB.

    Dipisah dari trigger_deployment agar mudah di-mock di unit test.
    """
    repo_dir: Path | None = None

    try:
        # --- 1. Set status deploying ---
        deployment_repository.update_status(
            db, deployment, DeploymentStatus.deploying
        )

        # --- 2. Validasi konfigurasi aplikasi ---
        if not app.repository:
            raise ValueError(
                f"Application {app.id} tidak memiliki repository URL yang dikonfigurasi."
            )

        # --- 3. Clone repository ---
        clone_result = git_service.clone_repository(
            url=app.repository,
            branch=deployment.branch,
            depth=1,
        )
        repo_dir = clone_result.repo_dir

        # Update commit SHA segera setelah clone
        deployment_repository.update_status(
            db,
            deployment,
            DeploymentStatus.deploying,
            commit_sha=clone_result.commit_sha,
        )

        # --- 4. Inject env vars ---
        raw_env_vars = env_var_repository.list_by_project(db, app.project_id)
        env_map: dict[str, str] = {}
        for ev in raw_env_vars:
            try:
                env_map[ev.key] = encryption_service.decrypt(ev.encrypted_value)
            except Exception as exc:
                logger.warning(f"Gagal dekripsi env var '{ev.key}': {exc}")

        if env_map:
            _write_env_file(repo_dir, env_map)

        # --- 5. Jalankan docker compose ---
        _run_compose(repo_dir, app.compose_path)

        # --- 6. Health check: pastikan container benar-benar running ---
        # Docker compose menggunakan nama direktori sebagai project name by default.
        compose_project = repo_dir.name
        hc_result = health_check_service.run_health_check(
            compose_project=compose_project,
            startup_delay=8.0,
            retries=3,
        )

        if not hc_result.healthy:
            raise RuntimeError(
                f"Health check gagal setelah deploy: {hc_result.message}"
            )

        # --- 7. Sukses ---
        deployment_repository.update_status(
            db, deployment, DeploymentStatus.success
        )
        logger.info(
            f"Deployment #{deployment.id} sukses "
            f"(app={app.id}, commit={clone_result.commit_sha[:8]}, "
            f"containers={hc_result.containers_checked})"
        )

    except Exception as exc:
        logger.error(f"Deployment #{deployment.id} gagal: {exc}")
        deployment_repository.update_status(
            db, deployment, DeploymentStatus.failed
        )
        raise RuntimeError(f"Deployment gagal: {exc}") from exc

    finally:
        if repo_dir is not None:
            git_service.cleanup(repo_dir)


def get_deployment(db: Session, deployment_id: int) -> Deployment | None:
    """Ambil satu deployment berdasarkan ID."""
    return deployment_repository.get_by_id(db, deployment_id)


def list_deployments(
    db: Session,
    application_ids: list[int],
    *,
    server_id: int | None = None,
    status: DeploymentStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Deployment]:
    """
    Daftar deployment history untuk sekumpulan application_id.
    Mendukung filter opsional (server_id, status) dan pagination (limit/offset).
    """
    return deployment_repository.list_all(
        db,
        application_ids,
        server_id=server_id,
        status=status,
        limit=limit,
        offset=offset,
    )


def list_deployments_by_application(
    db: Session,
    application_id: int,
    *,
    status: DeploymentStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Deployment]:
    """
    Daftar deployment history untuk satu aplikasi.
    Mendukung filter status dan pagination.
    """
    return deployment_repository.list_by_application(
        db,
        application_id,
        status=status,
        limit=limit,
        offset=offset,
    )
