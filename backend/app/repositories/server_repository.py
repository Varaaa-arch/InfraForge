"""
Repository layer untuk tabel servers.

Semua query/mutasi database server dilakukan di sini.
Service layer memanggil fungsi-fungsi ini, bukan langsung akses Session.
"""

from sqlalchemy.orm import Session

from app.models.server import Server, ServerStatus
from app.schemas.server import ServerCreate, ServerUpdate


def get_by_id(db: Session, server_id: int) -> Server | None:
    """Ambil server berdasarkan primary key. Return None jika tidak ditemukan."""
    return db.get(Server, server_id)


def get_by_id_and_owner(db: Session, server_id: int, owner_id: int) -> Server | None:
    """Ambil server yang dimiliki owner tertentu."""
    return (
        db.query(Server)
        .filter(Server.id == server_id, Server.owner_id == owner_id)
        .first()
    )


def list_by_owner(db: Session, owner_id: int) -> list[Server]:
    """Daftar semua server milik owner tertentu, diurutkan terbaru dulu."""
    return (
        db.query(Server)
        .filter(Server.owner_id == owner_id)
        .order_by(Server.created_at.desc())
        .all()
    )


def create(db: Session, owner_id: int, payload: ServerCreate) -> Server:
    """Buat entri server baru. Commit dan refresh dilakukan di sini."""
    server = Server(
        owner_id=owner_id,
        name=payload.name,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        auth_type=payload.auth_type,
        password=payload.password,
        private_key=payload.private_key,
        status=ServerStatus.inactive,
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    return server


def update(db: Session, server: Server, payload: ServerUpdate) -> Server:
    """
    Terapkan field-field yang tidak None dari payload ke model.
    Commit dan refresh dilakukan di sini.
    """
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(server, field, value)
    db.commit()
    db.refresh(server)
    return server


def update_status(db: Session, server: Server, status: ServerStatus) -> Server:
    """Update kolom status saja (dipanggil setelah tes koneksi SSH)."""
    server.status = status
    db.commit()
    db.refresh(server)
    return server


def delete(db: Session, server: Server) -> None:
    """Hapus server dari database."""
    db.delete(server)
    db.commit()
