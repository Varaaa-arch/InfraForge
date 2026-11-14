"""
Server Service — logika bisnis untuk manajemen server.

Mengorkestrasikan server_repository (CRUD database) dan ssh_service (tes koneksi).
Router API memanggil fungsi-fungsi di sini.
"""

from sqlalchemy.orm import Session

from loguru import logger

from app.models.server import Server, ServerStatus
from app.repositories import server_repository
from app.schemas.server import (
    ServerCreate,
    ServerExporterStatus,
    ServerUpdate,
    SSHTestResult,
)
from app.services import prometheus_service, ssh_service


def get_server(db: Session, server_id: int) -> Server | None:
    """Ambil server berdasarkan ID (tanpa filter owner)."""
    return server_repository.get_by_id(db, server_id)


def get_server_for_owner(db: Session, server_id: int, owner_id: int) -> Server | None:
    """Ambil server yang dimiliki owner tertentu."""
    return server_repository.get_by_id_and_owner(db, server_id, owner_id)


def list_servers(db: Session, owner_id: int) -> list[Server]:
    """Daftar semua server milik owner."""
    return server_repository.list_by_owner(db, owner_id)


def resolve_exporter_status(server: Server, up_map: dict[str, float]) -> ServerExporterStatus:
    """
    Status koneksi Prometheus untuk satu server.

    - ``not_configured`` — server belum mengisi ``exporter_instance``.
    - ``up`` / ``down`` — target terdaftar di Prometheus.
    - ``unknown`` — target tidak terdaftar atau Prometheus tidak dapat dihubungi.
    """
    if not server.exporter_instance:
        return "not_configured"
    value = up_map.get(server.exporter_instance)
    if value is None:
        return "unknown"
    return "up" if value == 1 else "down"


def list_exporter_statuses(servers: list[Server]) -> dict[int, ServerExporterStatus]:
    """Status koneksi Prometheus untuk daftar server (id server → status)."""
    try:
        up_map = prometheus_service.list_node_exporter_up()
    except RuntimeError as exc:
        logger.warning(f"Status exporter: Prometheus tidak dapat dihubungi: {exc}")
        up_map = {}

    return {
        server.id: resolve_exporter_status(server, up_map)
        for server in servers
    }


def count_servers(db: Session, owner_id: int) -> int:
    """Hitung jumlah server milik owner (untuk dashboard)."""
    return server_repository.count_by_owner(db, owner_id)


def count_servers_by_status(
    db: Session, owner_id: int, status: ServerStatus
) -> int:
    """Hitung server milik owner dengan status tertentu (untuk dashboard)."""
    return server_repository.count_by_owner_and_status(db, owner_id, status)


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
