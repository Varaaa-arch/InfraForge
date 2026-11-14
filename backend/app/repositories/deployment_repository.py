"""
Repository layer untuk tabel `deployments` (Task 3.6 + 3.7).

Perubahan Task 3.7:
- list_all mendukung filter opsional: server_id, status
- list_all dan list_by_application mendukung pagination: limit + offset
- update_status selalu mengisi finished_at untuk status terminal
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
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
    *,
    rollback_of: int | None = None,
    compose_path_snapshot: str | None = None,
    is_rollback: bool = False,
) -> Deployment:
    """
    Buat entri deployment baru dengan status `pending`.

    Args:
        rollback_of:           ID deployment sukses yang menjadi target rollback.
                               None untuk deployment biasa.
        compose_path_snapshot: Snapshot compose path dari deployment target rollback.
        is_rollback:           True jika ini adalah operasi rollback.

    Commit dan refresh dilakukan di sini.
    """
    deployment = Deployment(
        application_id=application_id,
        server_id=server_id,
        branch=branch,
        status=DeploymentStatus.pending,
        rollback_of=rollback_of,
        compose_path_snapshot=compose_path_snapshot,
        is_rollback=is_rollback,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return deployment


def count_by_application_ids(db: Session, application_ids: list[int]) -> int:
    """Hitung jumlah deployment untuk sekumpulan application_id (untuk dashboard)."""
    if not application_ids:
        return 0
    return (
        db.query(Deployment)
        .filter(Deployment.application_id.in_(application_ids))
        .count()
    )


def get_last_started_at(
    db: Session, application_ids: list[int]
) -> datetime | None:
    """
    ``started_at`` deployment terakhir untuk sekumpulan aplikasi.

    Dipakai untuk menentukan apakah env var project perlu re-deploy: env var
    yang diubah setelah waktu ini belum ikut terpasang di container yang jalan.

    Returns:
        Timestamp deployment terakhir, atau None bila belum ada deployment.
    """
    if not application_ids:
        return None
    last = (
        db.query(func.max(Deployment.started_at))
        .filter(Deployment.application_id.in_(application_ids))
        .scalar()
    )
    return last if isinstance(last, datetime) else None


def get_last_successful(
    db: Session,
    application_id: int,
    *,
    exclude_id: int | None = None,
) -> Deployment | None:
    """
    Ambil deployment sukses (status=success) terakhir untuk aplikasi tertentu.

    Dipakai oleh rollback untuk menemukan snapshot yang akan di-restore.

    Args:
        application_id: ID aplikasi yang dicari.
        exclude_id:     ID deployment yang dikecualikan (biasanya deployment
                        yang akan di-rollback itu sendiri, agar tidak
                        rollback ke diri sendiri).

    Returns:
        Deployment sukses terakhir, atau None jika tidak ada.
    """
    q = (
        db.query(Deployment)
        .filter(
            Deployment.application_id == application_id,
            Deployment.status == DeploymentStatus.success,
        )
    )
    if exclude_id is not None:
        q = q.filter(Deployment.id != exclude_id)
    return q.order_by(Deployment.finished_at.desc()).first()


def update_status(
    db: Session,
    deployment: Deployment,
    status: DeploymentStatus,
    commit_sha: str | None = None,
    log_path: str | None = None,
    compose_path_snapshot: str | None = None,
) -> Deployment:
    """
    Update status deployment.

    - `commit_sha`, `log_path`, `compose_path_snapshot` diupdate jika diberikan.
    - `finished_at` diisi otomatis saat status terminal (success / failed).
    - `compose_path_snapshot` disimpan saat status success agar bisa di-rollback.
    """
    deployment.status = status
    if commit_sha is not None:
        deployment.commit_sha = commit_sha
    if log_path is not None:
        deployment.log_path = log_path
    if compose_path_snapshot is not None:
        deployment.compose_path_snapshot = compose_path_snapshot
    if status in (DeploymentStatus.success, DeploymentStatus.failed):
        deployment.finished_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(deployment)
    return deployment
