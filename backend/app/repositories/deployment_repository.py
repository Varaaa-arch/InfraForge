"""
Repository layer untuk tabel `deployments` (Task 3.6 + 3.7).

Perubahan Task 3.7:
- list_all mendukung filter opsional: server_id, status
- list_all dan list_by_application mendukung pagination: limit + offset
- update_status selalu mengisi finished_at untuk status terminal
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.deployment import Deployment, DeploymentStatus


def get_by_id(db: Session, deployment_id: int) -> Deployment | None:
    """Ambil deployment berdasarkan primary key."""
    return db.get(Deployment, deployment_id)


def list_by_application(
    db: Session,
    application_id: int,
    *,
    status: DeploymentStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Deployment]:
    """
    Daftar deployment history untuk satu aplikasi dengan filter & pagination.

    Args:
        application_id: Filter wajib — ID aplikasi.
        status:         Filter opsional — hanya tampilkan deployment dengan status ini.
        limit:          Jumlah maksimal baris yang dikembalikan.
        offset:         Jumlah baris yang dilewati (untuk pagination).
    """
    q = (
        db.query(Deployment)
        .filter(Deployment.application_id == application_id)
    )
    if status is not None:
        q = q.filter(Deployment.status == status)
    return (
        q.order_by(Deployment.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def list_all(
    db: Session,
    application_ids: list[int],
    *,
    server_id: int | None = None,
    status: DeploymentStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Deployment]:
    """
    Daftar semua deployment untuk sekumpulan application_id dengan filter & pagination.

    Args:
        application_ids: List application_id milik user (dipakai sebagai whitelist).
        server_id:       Filter opsional — hanya deployment ke server ini.
        status:          Filter opsional — hanya deployment dengan status ini.
        limit:           Jumlah maksimal baris yang dikembalikan.
        offset:          Jumlah baris yang dilewati (untuk pagination).
    """
    if not application_ids:
        return []

    q = db.query(Deployment).filter(
        Deployment.application_id.in_(application_ids)
    )
    if server_id is not None:
        q = q.filter(Deployment.server_id == server_id)
    if status is not None:
        q = q.filter(Deployment.status == status)

    return (
        q.order_by(Deployment.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def create(
    db: Session,
    application_id: int,
    server_id: int | None,
    branch: str,
) -> Deployment:
    """
    Buat entri deployment baru dengan status `pending`.
    Commit dan refresh dilakukan di sini.
    """
    deployment = Deployment(
        application_id=application_id,
        server_id=server_id,
        branch=branch,
        status=DeploymentStatus.pending,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return deployment


def update_status(
    db: Session,
    deployment: Deployment,
    status: DeploymentStatus,
    commit_sha: str | None = None,
    log_path: str | None = None,
) -> Deployment:
    """
    Update status deployment.

    - `commit_sha` dan `log_path` diupdate jika diberikan (tidak None).
    - `finished_at` diisi otomatis saat status terminal (success / failed).
    """
    deployment.status = status
    if commit_sha is not None:
        deployment.commit_sha = commit_sha
    if log_path is not None:
        deployment.log_path = log_path
    if status in (DeploymentStatus.success, DeploymentStatus.failed):
        deployment.finished_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(deployment)
    return deployment
