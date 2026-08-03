"""
Repository layer untuk tabel `deployments`.

Semua query/mutasi database deployment dilakukan di sini.
Service layer memanggil fungsi-fungsi ini — tidak boleh akses Session langsung.
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
    limit: int = 50,
) -> list[Deployment]:
    """
    Daftar deployment history untuk satu aplikasi.
    Diurutkan terbaru dulu (started_at DESC). Default limit 50.
    """
    return (
        db.query(Deployment)
        .filter(Deployment.application_id == application_id)
        .order_by(Deployment.started_at.desc())
        .limit(limit)
        .all()
    )


def list_all(
    db: Session,
    application_ids: list[int],
    limit: int = 100,
) -> list[Deployment]:
    """
    Daftar semua deployment untuk sekumpulan application_id.
    Digunakan untuk menampilkan history lintas aplikasi milik satu user.
    """
    if not application_ids:
        return []
    return (
        db.query(Deployment)
        .filter(Deployment.application_id.in_(application_ids))
        .order_by(Deployment.started_at.desc())
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
    Update status deployment. Isi `finished_at` otomatis jika status terminal
    (success atau failed).
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
