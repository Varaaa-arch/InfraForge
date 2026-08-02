"""
Env Var Service — logika bisnis untuk environment variables.

Bertanggung jawab atas:
- Enkripsi value sebelum disimpan ke DB
- Dekripsi value saat dibaca dari DB
- Masking value untuk tampilan list
- Logika upsert (create jika belum ada, update jika sudah ada)
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.env_var import EnvVar
from app.repositories import env_var_repository
from app.schemas.env_var import (
    BulkUpsertResult,
    EnvVarBulkCreate,
    EnvVarMaskedResponse,
    EnvVarResponse,
)
from app.services import encryption_service


# ---------------------------------------------------------------------------
# Masking helper
# ---------------------------------------------------------------------------

def _mask_value(plaintext: str) -> str:
    """
    Samarkan value untuk ditampilkan di list view.
    Tampilkan 3 karakter pertama + "****" (atau full mask jika kurang dari 3 karakter).

    Contoh:
        "postgres://user:pass@host/db" → "pos****"
        "abc"                          → "abc****"
        "xy"                           → "****"
    """
    if len(plaintext) <= 2:
        return "****"
    return plaintext[:3] + "****"


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def _to_response(env_var: EnvVar) -> EnvVarResponse:
    """Dekripsi value dan bungkus ke EnvVarResponse."""
    plaintext = encryption_service.decrypt(env_var.encrypted_value)
    return EnvVarResponse(
        id=env_var.id,
        project_id=env_var.project_id,
        key=env_var.key,
        value=plaintext,
        created_at=env_var.created_at,
        updated_at=env_var.updated_at,
    )


def _to_masked_response(env_var: EnvVar) -> EnvVarMaskedResponse:
    """Dekripsi value, masking, dan bungkus ke EnvVarMaskedResponse."""
    plaintext = encryption_service.decrypt(env_var.encrypted_value)
    return EnvVarMaskedResponse(
        id=env_var.id,
        project_id=env_var.project_id,
        key=env_var.key,
        masked_value=_mask_value(plaintext),
        created_at=env_var.created_at,
        updated_at=env_var.updated_at,
    )


# ---------------------------------------------------------------------------
# Public API (dipanggil oleh router)
# ---------------------------------------------------------------------------

@dataclass
class _UpsertOutcome:
    env_var: EnvVar
    created: bool


def upsert_env_var(db: Session, project_id: int, key: str, plaintext_value: str) -> _UpsertOutcome:
    """
    Upsert satu env var:
    - Jika key belum ada → create baru
    - Jika key sudah ada → update value
    Value dienkripsi sebelum masuk ke repository.
    """
    encrypted = encryption_service.encrypt(plaintext_value)
    existing = env_var_repository.get_by_project_and_key(db, project_id, key)

    if existing is None:
        env_var = env_var_repository.create(db, project_id, key, encrypted)
        return _UpsertOutcome(env_var=env_var, created=True)
    else:
        env_var = env_var_repository.update_value(db, existing, encrypted)
        return _UpsertOutcome(env_var=env_var, created=False)


def bulk_upsert(
    db: Session, project_id: int, payload: EnvVarBulkCreate
) -> tuple[list[EnvVarResponse], BulkUpsertResult]:
    """
    Bulk upsert — proses setiap item di payload.env_vars.
    Returns tuple (list respons penuh, ringkasan statistik).
    """
    created_count = 0
    updated_count = 0
    responses: list[EnvVarResponse] = []

    for item in payload.env_vars:
        outcome = upsert_env_var(db, project_id, item.key, item.value)
        responses.append(_to_response(outcome.env_var))
        if outcome.created:
            created_count += 1
        else:
            updated_count += 1

    summary = BulkUpsertResult(
        created=created_count,
        updated=updated_count,
        total=created_count + updated_count,
    )
    return responses, summary


def list_env_vars_masked(db: Session, project_id: int) -> list[EnvVarMaskedResponse]:
    """
    Daftar env var dengan value yang disamarkan (untuk dashboard/list view).
    """
    env_vars = env_var_repository.list_by_project(db, project_id)
    return [_to_masked_response(ev) for ev in env_vars]


def get_env_var(db: Session, project_id: int, env_var_id: int) -> EnvVarResponse | None:
    """
    Ambil detail satu env var dengan value plaintext (untuk editor/reveal).
    Return None jika tidak ditemukan atau bukan milik project ini.
    """
    ev = env_var_repository.get_by_project_and_id(db, project_id, env_var_id)
    if ev is None:
        return None
    return _to_response(ev)


def delete_env_var(db: Session, project_id: int, env_var_id: int) -> bool:
    """
    Hapus satu env var.
    Returns True jika berhasil, False jika tidak ditemukan.
    """
    ev = env_var_repository.get_by_project_and_id(db, project_id, env_var_id)
    if ev is None:
        return False
    env_var_repository.delete(db, ev)
    return True
