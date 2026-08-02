"""
Repository layer untuk tabel `applications`.

Semua query/mutasi database aplikasi dilakukan di sini.
Service layer memanggil fungsi-fungsi ini — tidak perlu akses Session secara langsung.
"""

from sqlalchemy.orm import Session

from app.models.application import AppStatus, Application
from app.schemas.application import ApplicationCreate, ApplicationUpdate


def get_by_id(db: Session, application_id: int) -> Application | None:
    """Ambil aplikasi berdasarkan primary key."""
    return db.get(Application, application_id)


def get_by_id_and_project(
    db: Session, application_id: int, project_id: int
) -> Application | None:
    """Ambil aplikasi yang dimiliki project tertentu."""
    return (
        db.query(Application)
        .filter(
            Application.id == application_id,
            Application.project_id == project_id,
        )
        .first()
    )


def list_by_project(db: Session, project_id: int) -> list[Application]:
    """Daftar semua aplikasi dalam sebuah project, diurutkan terbaru dulu."""
    return (
        db.query(Application)
        .filter(Application.project_id == project_id)
        .order_by(Application.created_at.desc())
        .all()
    )


def list_all_by_owner(db: Session, owner_project_ids: list[int]) -> list[Application]:
    """
    Daftar semua aplikasi lintas project milik owner.
    Menerima list project_id milik owner untuk filter.
    """
    if not owner_project_ids:
        return []
    return (
        db.query(Application)
        .filter(Application.project_id.in_(owner_project_ids))
        .order_by(Application.created_at.desc())
        .all()
    )


def create(db: Session, payload: ApplicationCreate) -> Application:
    """Buat entri aplikasi baru."""
    app = Application(
        project_id=payload.project_id,
        name=payload.name,
        repository=payload.repository,
        branch=payload.branch,
        dockerfile_path=payload.dockerfile_path,
        compose_path=payload.compose_path,
        build_context=payload.build_context,
        status=AppStatus.idle,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def update(db: Session, application: Application, payload: ApplicationUpdate) -> Application:
    """
    Terapkan field-field yang tidak None dari payload ke model.
    Menggunakan exclude_unset=True agar field yang tidak dikirim tidak diubah.
    """
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(application, field, value)
    db.commit()
    db.refresh(application)
    return application


def update_status(db: Session, application: Application, status: AppStatus) -> Application:
    """Update status operasional aplikasi (idle → deploying → running/failed)."""
    application.status = status
    db.commit()
    db.refresh(application)
    return application


def delete(db: Session, application: Application) -> None:
    """Hapus aplikasi dari database."""
    db.delete(application)
    db.commit()


def count_by_project(db: Session, project_id: int) -> int:
    """Hitung jumlah aplikasi dalam sebuah project (untuk dashboard)."""
    return db.query(Application).filter(Application.project_id == project_id).count()
