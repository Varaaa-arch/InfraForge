"""
Deployment Service — orkestrasi alur deployment (Task 3.6 + Task 3.8 + Task 3.9).

Alur eksekusi `_run_deployment`:
  1. Set status → deploying.
  2. Buat log file di tmp/ dan simpan log_path ke DB.
  3. Validasi konfigurasi (repository URL wajib ada).
  4. Clone repository via git_service (ke tmp/).
  5. Inject env vars dari DB ke .env di direktori clone.
  6. Jalankan docker compose build + up -d (output ditulis ke log file).
  7. Panggil run_health_check → cek status container setelah startup.
  8. Jika healthy → set status success.
     Jika unhealthy → raise RuntimeError → set status failed.
  9. Jika ada Exception → set status failed, re-raise.
 10. Cleanup tmp/ di finally block.

Log file:
  Setiap baris output dari git clone / docker compose ditulis ke file
  tmp/deployment_<id>.log sehingga WebSocket handler bisa meng-stream-nya
  ke client secara real-time.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application import AppStatus
from app.models.deployment import Deployment, DeploymentStatus
from app.models.server import Server
from app.repositories import application_repository
from app.repositories import deployment_repository
from app.repositories import env_var_repository
from app.repositories import server_repository
from app.services import encryption_service
from app.services import git_service
from app.services import health_check as health_check_service
from app.utils.env_sanitizer import build_env_file_line


# ---------------------------------------------------------------------------
# Internal helpers (dipisah agar bisa di-mock di unit test)
# ---------------------------------------------------------------------------

def _make_log_file(deployment_id: int) -> Path:
    """
    Buat file log kosong di direktori tmp sistem.

    File dibuat dengan nama deterministik `deployment_<id>.log` sehingga
    WebSocket handler bisa menemukan file ini berdasarkan deployment_id.

    Returns:
        Path ke file log yang sudah dibuat.
    """
    tmp_dir = Path(tempfile.gettempdir())
    log_file = tmp_dir / f"deployment_{deployment_id}.log"
    log_file.touch()
    return log_file


def _append_log(log_file: Path, text: str) -> None:
    """
    Tulis/append teks ke file log deployment.

    Setiap pemanggilan disambung ke akhir file (mode 'a').
    Baris kosong dan spasi trailing tetap ditulis apa adanya.
    """
    with log_file.open("a", encoding="utf-8") as f:
        f.write(text)


def _write_env_file(repo_dir: Path, env_vars: dict[str, str]) -> Path:
    """
    Tulis dictionary key=value ke file `.env` di dalam `repo_dir`.

    Setiap baris disanitasi via `build_env_file_line()`:
      - Key di-uppercase dan divalidasi format.
      - Value di-strip karakter kontrol berbahaya (defense-in-depth).
      - Value yang mengandung spasi atau karakter khusus di-double-quote.
      - Value yang mengandung backslash/double-quote di-escape.

    Ini adalah lapisan keamanan kedua (output layer). Lapisan pertama
    (input layer) ada di `EnvVarCreate` schema via `field_validator`.

    Return path file .env yang dibuat.
    """
    env_file = repo_dir / ".env"
    lines: list[str] = []
    skipped = 0

    for k, v in env_vars.items():
        try:
            lines.append(build_env_file_line(k, v))
        except ValueError as exc:
            # Jika sanitasi gagal (key/value tidak valid), skip dan log warning
            # Jangan crash seluruh deployment hanya karena satu env var bermasalah
            logger.warning(f"Env var '{k}' di-skip saat tulis .env: {exc}")
            skipped += 1

    env_file.write_text("".join(lines), encoding="utf-8")
    logger.debug(
        f"Wrote {len(lines)} env vars to {env_file}"
        + (f" ({skipped} skipped due to sanitization errors)" if skipped else "")
    )
    return env_file


def _run_compose(
    repo_dir: Path,
    compose_file: str,
    log_file: Path | None = None,
) -> tuple[str, str]:
    """
    Jalankan `docker compose -f <compose_file> build` lalu
    `docker compose -f <compose_file> up -d` via subprocess.

    Output (stdout + stderr) setiap perintah ditulis ke `log_file` jika
    diberikan, sehingga WebSocket handler bisa meng-stream log secara
    real-time.

    Returns:
        Tuple (stdout_combined, stderr_combined).

    Raises:
        RuntimeError jika salah satu perintah exit non-zero.
    """
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []

    for args in [
        ["docker", "compose", "-f", compose_file, "build", "--no-cache"],
        ["docker", "compose", "-f", compose_file, "up", "-d"],
    ]:
        header = f"[InfraForge] Running: {' '.join(args)}\n"
        logger.info(f"Running: {' '.join(args)} in {repo_dir}")
        if log_file is not None:
            _append_log(log_file, header)

        result = subprocess.run(
            args,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=600,  # 10 menit per perintah
        )
        stdout_parts.append(result.stdout)
        stderr_parts.append(result.stderr)

        # Tulis output ke log file
        if log_file is not None:
            combined = result.stdout
            if result.stderr:
                combined += result.stderr
            if combined:
                _append_log(log_file, combined)

        if result.returncode != 0:
            error_msg = (
                f"Command '{' '.join(args)}' gagal (exit {result.returncode}):\n"
                f"{result.stderr}"
            )
            if log_file is not None:
                _append_log(log_file, f"[InfraForge] ERROR: {error_msg}\n")
            raise RuntimeError(error_msg)

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
    Trigger deployment baru (synchronous — untuk API manual trigger).

    Concurrency guard (double-guard):
      1. Cek Redis lock → jika ada lock aktif, raise ConflictError.
      2. Cek DB app.status → fallback jika Redis down.
      3. Acquire lock sebelum menjalankan deployment.
      4. Release lock di finally block.

    Raises:
        ValueError:  Jika aplikasi atau server tidak ditemukan.
        RuntimeError: Jika deployment gagal atau aplikasi sedang deploying.
    """
    from app.services.deployment_queue import (
        acquire_deploy_lock,
        get_running_deployment_id,
        is_deployment_running,
        is_locked_by_db_status,
        release_deploy_lock,
    )

    # --- Guard layer 1: Redis lock ---
    if is_deployment_running(application_id):
        running_id = get_running_deployment_id(application_id)
        raise RuntimeError(
            f"Application {application_id} sedang dalam proses deployment "
            f"(deployment_id={running_id}). Tunggu hingga selesai sebelum memicu ulang."
        )

    # --- Guard layer 2: DB status fallback ---
    if is_locked_by_db_status(application_id):
        raise RuntimeError(
            f"Application {application_id} berstatus 'deploying' di database. "
            f"Tunggu hingga deployment aktif selesai."
        )

    deployment, app, server = create_deployment_record(
        db, application_id, server_id, branch_override
    )

    # Acquire lock setelah record dibuat (deployment_id sudah tersedia)
    acquired = acquire_deploy_lock(application_id, deployment.id)
    if not acquired:
        # Race condition: lock diambil oleh proses lain setelah cek di atas
        deployment_repository.update_status(db, deployment, DeploymentStatus.failed)
        running_id = get_running_deployment_id(application_id)
        raise RuntimeError(
            f"Application {application_id} sedang dalam proses deployment "
            f"(deployment_id={running_id}). Race condition terdeteksi."
        )

    # Update app.status = deploying
    application_repository.update_status(db, app, AppStatus.deploying)

    try:
        _run_deployment(db, deployment, app, server)
        # Sukses → set app.status = running
        application_repository.update_status(db, app, AppStatus.running)
    except Exception:
        # Gagal → set app.status = failed
        application_repository.update_status(db, app, AppStatus.failed)
        logger.error(
            f"Deployment #{deployment.id} untuk app={application_id} gagal."
        )
        raise
    finally:
        release_deploy_lock(application_id)

    return deployment


def create_deployment_record(
    db: Session,
    application_id: int,
    server_id: int,
    branch_override: str | None = None,
) -> tuple[Deployment, Application, Server]:
    """
    Validasi aplikasi dan server, lalu buat record Deployment (status=pending).

    Dipisah dari trigger_deployment agar webhook handler bisa membuat record
    terlebih dahulu, lalu men-enqueue job ke ARQ untuk eksekusi async.

    Returns:
        Tuple (deployment, application, server) — siap dipakai oleh _run_deployment.

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
    return deployment, app, server


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
    log_file: Path | None = None

    try:
        # --- 1. Set status deploying ---
        deployment_repository.update_status(
            db, deployment, DeploymentStatus.deploying
        )

        # --- 2. Buat log file dan simpan path ke DB ---
        log_file = _make_log_file(deployment.id)
        _append_log(
            log_file,
            f"[InfraForge] Deployment #{deployment.id} dimulai.\n",
        )
        deployment_repository.update_status(
            db,
            deployment,
            DeploymentStatus.deploying,
            log_path=str(log_file),
        )

        # --- 3. Validasi konfigurasi aplikasi ---
        if not app.repository:
            raise ValueError(
                f"Application {app.id} tidak memiliki repository URL yang dikonfigurasi."
            )

        # --- 4. Clone repository ---
        _append_log(
            log_file,
            f"[InfraForge] Cloning {app.repository} branch={deployment.branch} ...\n",
        )
        clone_result = git_service.clone_repository(
            url=app.repository,
            branch=deployment.branch,
            depth=1,
        )
        repo_dir = clone_result.repo_dir
        _append_log(
            log_file,
            f"[InfraForge] Clone selesai. commit={clone_result.commit_sha}\n",
        )

        # Update commit SHA segera setelah clone
        deployment_repository.update_status(
            db,
            deployment,
            DeploymentStatus.deploying,
            commit_sha=clone_result.commit_sha,
        )

        # --- 5. Inject env vars ---
        raw_env_vars = env_var_repository.list_by_project(db, app.project_id)
        env_map: dict[str, str] = {}
        for ev in raw_env_vars:
            try:
                env_map[ev.key] = encryption_service.decrypt(ev.encrypted_value)
            except Exception as exc:
                logger.warning(f"Gagal dekripsi env var '{ev.key}': {exc}")

        if env_map:
            _write_env_file(repo_dir, env_map)
            _append_log(
                log_file,
                f"[InfraForge] Injected {len(env_map)} env vars.\n",
            )

        # --- 6. Jalankan docker compose (output ke log file) ---
        _append_log(log_file, "[InfraForge] Menjalankan docker compose build + up...\n")
        _run_compose(repo_dir, app.compose_path, log_file=log_file)
        _append_log(log_file, "[InfraForge] docker compose selesai.\n")

        # --- 7. Health check: pastikan container benar-benar running ---
        compose_project = repo_dir.name
        _append_log(
            log_file,
            f"[InfraForge] Menjalankan health check (project={compose_project})...\n",
        )
        hc_result = health_check_service.run_health_check(
            compose_project=compose_project,
            startup_delay=8.0,
            retries=3,
        )

        if not hc_result.healthy:
            raise RuntimeError(
                f"Health check gagal setelah deploy: {hc_result.message}"
            )

        # --- 8. Sukses ---
        _append_log(
            log_file,
            f"[InfraForge] Deployment #{deployment.id} SUKSES.\n",
        )
        deployment_repository.update_status(
            db, deployment, DeploymentStatus.success,
            compose_path_snapshot=app.compose_path,
        )
        logger.info(
            f"Deployment #{deployment.id} sukses "
            f"(app={app.id}, commit={clone_result.commit_sha[:8]}, "
            f"containers={hc_result.containers_checked})"
        )

    except Exception as exc:
        logger.error(f"Deployment #{deployment.id} gagal: {exc}")
        if log_file is not None:
            _append_log(
                log_file,
                f"[InfraForge] Deployment #{deployment.id} GAGAL: {exc}\n",
            )
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


def rollback_deployment(
    db: Session,
    target_deployment_id: int,
    application_id: int,
) -> Deployment:
    """
    Rollback ke state deployment sukses sebelumnya.

    Flow:
      1. Validasi target deployment: harus ada + status success + milik app ini.
      2. Cek concurrency lock (double-guard seperti trigger_deployment).
      3. Ambil snapshot dari target: branch, commit_sha, compose_path_snapshot.
      4. Buat Deployment record baru (is_rollback=True, rollback_of=target_id).
      5. Jalankan _run_deployment dengan compose_path dari snapshot.

    Args:
        target_deployment_id: ID deployment sukses yang akan di-rollback ke sana.
        application_id:       ID aplikasi (untuk validasi kepemilikan + lock).

    Returns:
        Deployment record baru yang merepresentasikan operasi rollback.

    Raises:
        ValueError:   Jika target deployment tidak ditemukan, bukan milik app ini,
                      atau bukan status success.
        RuntimeError: Jika aplikasi sedang deploying (concurrency guard),
                      atau proses rollback gagal.
    """
    from app.services.deployment_queue import (
        acquire_deploy_lock,
        get_running_deployment_id,
        is_deployment_running,
        is_locked_by_db_status,
        release_deploy_lock,
    )

    # --- 1. Validasi target deployment ---
    target = deployment_repository.get_by_id(db, target_deployment_id)
    if target is None:
        raise ValueError(f"Deployment #{target_deployment_id} tidak ditemukan.")

    if target.application_id != application_id:
        raise ValueError(
            f"Deployment #{target_deployment_id} bukan milik aplikasi {application_id}."
        )

    if target.status != DeploymentStatus.success:
        raise ValueError(
            f"Rollback hanya bisa ke deployment dengan status 'success'. "
            f"Deployment #{target_deployment_id} berstatus '{target.status.value}'."
        )

    # Pastikan ada snapshot compose_path (deployment lama mungkin tidak punya)
    compose_path = target.compose_path_snapshot
    if not compose_path:
        # Fallback: ambil dari konfigurasi aplikasi saat ini
        app = application_repository.get_by_id(db, application_id)
        if app is None:
            raise ValueError(f"Application {application_id} tidak ditemukan.")
        compose_path = app.compose_path
        logger.warning(
            f"Deployment #{target_deployment_id} tidak punya compose_path_snapshot, "
            f"fallback ke app.compose_path='{compose_path}'"
        )

    # --- 2. Concurrency guard ---
    if is_deployment_running(application_id):
        running_id = get_running_deployment_id(application_id)
        raise RuntimeError(
            f"Application {application_id} sedang dalam proses deployment "
            f"(deployment_id={running_id}). Tunggu hingga selesai sebelum rollback."
        )

    if is_locked_by_db_status(application_id):
        raise RuntimeError(
            f"Application {application_id} berstatus 'deploying' di database. "
            f"Tunggu hingga deployment aktif selesai."
        )

    # --- 3. Ambil app + server ---
    app = application_repository.get_by_id(db, application_id)
    if app is None:
        raise ValueError(f"Application {application_id} tidak ditemukan.")

    server = server_repository.get_by_id(db, target.server_id) if target.server_id else None
    if server is None:
        raise ValueError(
            f"Server dari deployment #{target_deployment_id} tidak ditemukan atau sudah dihapus. "
            "Gunakan trigger_deployment biasa dengan server yang masih aktif."
        )

    # --- 4. Buat Deployment record rollback ---
    rollback_dep = deployment_repository.create(
        db,
        application_id=application_id,
        server_id=server.id,
        branch=target.branch,
        rollback_of=target_deployment_id,
        compose_path_snapshot=compose_path,
        is_rollback=True,
    )

    # --- 5. Acquire lock + jalankan rollback ---
    acquired = acquire_deploy_lock(application_id, rollback_dep.id)
    if not acquired:
        deployment_repository.update_status(db, rollback_dep, DeploymentStatus.failed)
        running_id = get_running_deployment_id(application_id)
        raise RuntimeError(
            f"Application {application_id} sedang dalam proses deployment "
            f"(deployment_id={running_id}). Race condition terdeteksi."
        )

    # Update app.status = deploying
    application_repository.update_status(db, app, AppStatus.deploying)

    try:
        # Jalankan deployment dengan compose_path dari snapshot
        # Override compose_path di app object (tidak di-commit ke DB)
        app.compose_path = compose_path
        _run_deployment(db, rollback_dep, app, server)
        application_repository.update_status(db, app, AppStatus.running)
    except Exception:
        application_repository.update_status(db, app, AppStatus.failed)
        logger.error(
            f"Rollback deployment #{rollback_dep.id} "
            f"(target={target_deployment_id}) gagal."
        )
        raise
    finally:
        release_deploy_lock(application_id)

    logger.info(
        f"Rollback #{rollback_dep.id} sukses "
        f"(app={application_id}, target=#{target_deployment_id}, "
        f"branch={target.branch}, compose={compose_path})"
    )
    return rollback_dep
