"""
Encryption Service — enkripsi/dekripsi simetris menggunakan Fernet (AES-128-CBC + HMAC).

Fernet menjamin:
- Ciphertext tidak bisa dibaca tanpa kunci yang benar
- Ciphertext yang dimodifikasi akan gagal dekripsi (authenticated encryption)
- Setiap enkripsi menghasilkan ciphertext yang berbeda (random IV)

Kunci Fernet harus berupa 32-byte URL-safe base64.
Kita derive dari ENCRYPTION_KEY (hex string) atau SECRET_KEY menggunakan
SHA-256 + base64url encoding agar selalu valid tanpa memaksa format tertentu
di .env.

Penggunaan:
    from app.services.encryption_service import encrypt, decrypt

    ciphertext = encrypt("DATABASE_URL=postgres://...")
    plaintext  = decrypt(ciphertext)
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _build_fernet_key() -> bytes:
    """
    Derive kunci Fernet 32-byte dari ENCRYPTION_KEY atau SECRET_KEY.

    Algoritma:
      1. Ambil ENCRYPTION_KEY jika ada, fallback ke SECRET_KEY
      2. SHA-256 → 32 raw bytes
      3. base64url encode → format yang valid untuk Fernet
    """
    raw_key = getattr(settings, "ENCRYPTION_KEY", None) or settings.SECRET_KEY
    digest = hashlib.sha256(raw_key.encode()).digest()  # 32 bytes
    return base64.urlsafe_b64encode(digest)  # Fernet key format


# Satu instance global — di-instantiate sekali saat modul di-load.
# Aman karena Fernet bersifat stateless (kunci tidak berubah saat runtime).
_fernet: Fernet = Fernet(_build_fernet_key())


def encrypt(plaintext: str) -> str:
    """
    Enkripsi string plaintext → ciphertext string (URL-safe base64).

    Args:
        plaintext: Nilai yang akan dienkripsi (misal "postgres://user:pass@host/db")

    Returns:
        String ciphertext yang aman disimpan di database.
    """
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """
    Dekripsi ciphertext string → plaintext string.

    Args:
        ciphertext: Nilai terenkripsi yang disimpan di database.

    Returns:
        Nilai asli (plaintext).

    Raises:
        ValueError: Jika ciphertext rusak, dimodifikasi, atau kunci salah.
    """
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Dekripsi gagal: ciphertext tidak valid atau kunci enkripsi tidak cocok."
        ) from exc


def rotate_key(old_ciphertext: str, new_fernet: Fernet) -> str:
    """
    Re-enkripsi ciphertext lama dengan kunci baru (key rotation helper).

    Berguna saat ENCRYPTION_KEY dirotasi — panggil ini untuk setiap value
    di database sebelum mengganti kunci aktif.

    Args:
        old_ciphertext: Ciphertext yang dienkripsi dengan kunci lama (_fernet saat ini).
        new_fernet:     Instance Fernet dengan kunci baru.

    Returns:
        Ciphertext baru yang dienkripsi dengan new_fernet.
    """
    plaintext = decrypt(old_ciphertext)
    return new_fernet.encrypt(plaintext.encode()).decode()
