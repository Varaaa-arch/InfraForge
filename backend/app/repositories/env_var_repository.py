"""
Repository layer untuk tabel `project_env_vars`.

Semua query/mutasi database env var dilakukan di sini.
Kolom `encrypted_value` di sini masih raw — enkripsi/dekripsi
dilakukan di service layer sebelum memanggil fungsi-fungsi ini.
"""

from sqlalchemy.orm import Session

from app.models.env_var import EnvVar


def get_by_id(db: Session, env_var_id: int) -> EnvVar | None:
    """Ambil satu env var berdasarkan primary key."""
    return db.get(EnvVar, env_var_id)


def get_by_project_and_id(db: Session, project_id: int, env_var_id: int) -> EnvVar | None:
    """Ambil env var yang dimiliki project tertentu."""
    return (
        db.query(EnvVar)
        .filter(EnvVar.id == env_var_id, EnvVar.project_id == project_id)
        .first()
    )


def get_by_project_and_key(db: Session, project_id: int, key: str) -> EnvVar | None:
    """Cari env var berdasarkan project_id + key (untuk upsert)."""
    return (
        db.query(EnvVar)
        .filter(EnvVar.project_id == project_id, EnvVar.key == key)
        .first()
    )


def list_by_project(db: Session, project_id: int) -> list[EnvVar]:
    """Daftar semua env var milik sebuah project, diurutkan alfabet."""
    return (
        db.query(EnvVar)
        .filter(EnvVar.project_id == project_id)
        .order_by(EnvVar.key.asc())
        .all()
    )


def create(db: Session, project_id: int, key: str, encrypted_value: str) -> EnvVar:
    """Buat env var baru. encrypted_value sudah harus terenkripsi."""
    env_var = EnvVar(
        project_id=project_id,
        key=key,
        encrypted_value=encrypted_value,
    )
    db.add(env_var)
    db.commit()
    db.refresh(env_var)
    return env_var


def update_value(db: Session, env_var: EnvVar, encrypted_value: str) -> EnvVar:
    """Update encrypted_value dari env var yang sudah ada."""
    env_var.encrypted_value = encrypted_value
    db.commit()
    db.refresh(env_var)
    return env_var


def delete(db: Session, env_var: EnvVar) -> None:
    """Hapus satu env var."""
    db.delete(env_var)
    db.commit()


def delete_all_by_project(db: Session, project_id: int) -> int:
    """
    Hapus semua env vars milik sebuah project.
    Returns jumlah baris yang dihapus.
    """
    count = (
        db.query(EnvVar)
        .filter(EnvVar.project_id == project_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return count
