"""
Pydantic schemas untuk endpoint env vars.

Prinsip keamanan:
- EnvVarResponse TIDAK mengekspos encrypted_value mentah dari DB.
  Nilai plaintext dikembalikan di field `value` (sudah didekripsi oleh service).
- EnvVarMaskedResponse mengembalikan value yang disamarkan (untuk list view).
"""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Regex untuk nama env var yang valid (konvensi POSIX: huruf besar, angka, underscore)
_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class EnvVarCreate(BaseModel):
    """Satu env var untuk di-create atau di-upsert."""

    key: str = Field(
        min_length=1,
        max_length=255,
        description="Nama variabel (contoh: DATABASE_URL, JWT_SECRET)",
    )
    value: str = Field(
        min_length=1,
        description="Nilai plaintext — akan dienkripsi sebelum disimpan ke DB",
    )

    @field_validator("key")
    @classmethod
    def validate_key_format(cls, v: str) -> str:
        if not _ENV_KEY_PATTERN.match(v):
            raise ValueError(
                "key hanya boleh berisi huruf, angka, dan underscore, "
                "serta tidak boleh diawali angka"
            )
        return v.upper()  # Normalisasi ke uppercase (konvensi env var)


class EnvVarBulkCreate(BaseModel):
    """Payload bulk upsert — kirim beberapa env var sekaligus."""

    env_vars: list[EnvVarCreate] = Field(
        min_length=1,
        description="Daftar env vars yang akan di-upsert",
    )


class EnvVarUpdate(BaseModel):
    """Payload update value saja (key tidak bisa diubah)."""

    value: str = Field(min_length=1, description="Nilai plaintext baru")


class EnvVarResponse(BaseModel):
    """Response lengkap — value sudah didekripsi (visible untuk owner)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    key: str
    value: str  # plaintext, bukan encrypted_value dari DB
    created_at: datetime
    updated_at: datetime


class EnvVarMaskedResponse(BaseModel):
    """
    Response untuk list view — value disamarkan.
    Hanya tampilkan 3 karakter pertama + masking.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    key: str
    masked_value: str
    created_at: datetime
    updated_at: datetime


class BulkUpsertResult(BaseModel):
    """Ringkasan hasil operasi bulk upsert."""

    created: int = Field(description="Jumlah env var baru yang dibuat")
    updated: int = Field(description="Jumlah env var yang diperbarui")
    total: int = Field(description="Total env var yang diproses")
