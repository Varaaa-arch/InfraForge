"""
Application Service — logika bisnis untuk manajemen aplikasi.

Layer ini mengabstraksi akses repository dan menyediakan API bersih
yang dipanggil oleh router. Semua validasi bisnis (bukan hanya schema)
ditangani di sini.
"""

from sqlalchemy.orm import Session

from app.models.application import AppStatus, Application
from app.models.project import Project
from app.repositories import application_repository
from app.schemas.application import ApplicationCreate, ApplicationUpdate


def get_application(db: Session, application_id: int) -> Application | None:
    """Ambil aplikasi berdasarkan ID (tanpa filter project)."""
    return application_repository.get_by_id(db, application_id)


def get_application_for_project(
    db: Session, application_id: int, project_id: int
) -> Application | None:
    """Ambil aplikasi yang dimiliki project tertentu."""
    return application_repository.get_by_id_and_project(db, application_id, project_id)


def list_applications_by_project(db: Session, project_id: int) -> list[Application]:
    """Daftar aplikasi dalam satu project."""
    return application_repository.list_by_project(db, project_id)


def list_applications_for_owner(
    db: Session, owner_project_ids: list[int]
) -> list[Application]:
    """
    Daftar semua aplikasi yang dimiliki user (lintas project).
    Menerima list project_id milik user sebagai filter.
    """
    return application_repository.list_all_by_owner(db, owner_project_ids)


def create_application(db: Session, payload: ApplicationCreate) -> Application:
    """
    Buat aplikasi baru.
    Validasi bahwa project_id valid dilakukan di layer router (tidak di sini)
    agar responsibility tetap jelas.
    """
    return application_repository.create(db, payload)


def update_application(
    db: Session, application: Application, payload: ApplicationUpdate
) -> Application:
    """Update field konfigurasi aplikasi."""
    return application_repository.update(db, application, payload)


def update_application_status(
    db: Session, application: Application, status: AppStatus
) -> Application:
    """
    Update status operasional aplikasi.
    Dipanggil oleh deployment engine / webhook handler.
    """
    return application_repository.update_status(db, application, status)


def delete_application(db: Session, application: Application) -> None:
    """Hapus aplikasi dari database."""
    application_repository.delete(db, application)


def count_by_project(db: Session, project_id: int) -> int:
    """Hitung jumlah aplikasi per project (untuk dashboard/stats)."""
    return application_repository.count_by_project(db, project_id)
