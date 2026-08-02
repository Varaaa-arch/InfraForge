"""
Server Service — logika bisnis untuk manajemen server.

Mengorkestrasikan server_repository (CRUD database) dan ssh_service (tes koneksi).
Router API memanggil fungsi-fungsi di sini.
"""

from sqlalchemy.orm import Session

from app import repositories
from app.models.server import Server
from app.repositories import server_repository
from app.schemas.server import ServerCreate, ServerUpdate, SSHTestResult
from app.services import ssh_service


def get_server(db: Session, server_id: int) -> Server | None:
    """Ambil server berdasarkan ID (tanpa filter owner)."""
    return server_repository.get_by_id(db, server_id)


def get_server_for_owner(db: Session, server_id: int, owner_id: int) -> Server | None:
    """Ambil server yang dimiliki owner tertentu."""
    return server_repository.get_by_id_and_owner(db, server_id, owner_id)


def list_servers(db: Session, owner_id: int) -> list[Server]:
    """Daftar semua server milik owner."""
    return server_repository.list_by_owner(db, owner_id)


def create_server(db: Session, owner_id: int, payload: ServerCreate) -> Server:
    """Buat server baru dan simpan ke database."""
    return server_repository.create(db, owner_id, payload)


def update_server(db: Session, server: Server, payload: ServerUpdate) -> Server:
    """Update field server yang diberikan di payload."""
    return server_repository.update(db, server, payload)


def delete_server(db: Session, server: Server) -> None:
    """Hapus server dari database."""
    server_repository.delete(db, server)


def test_server_connection(db: Session, server: Server) -> SSHTestResult:
    """
    Jalankan tes koneksi SSH ke server.

    Setelah tes selesai, update status server di database:
    - active  → koneksi berhasil
    - error   → koneksi gagal
    """
    result = ssh_service.test_connection(server)
    new_status = ssh_service.resolve_new_status(result)
    server_repository.update_status(db, server, new_status)
    return result
