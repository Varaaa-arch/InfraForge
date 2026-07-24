from loguru import logger

from app.database.redis_client import redis_client


def _key(jti: str) -> str:
    return f"blocklist:{jti}"


def blocklist_token(jti: str, expires_in_seconds: int) -> None:
    """Tandai sebuah token (lewat jti-nya) supaya gak bisa dipakai lagi.

    TTL-nya disamain sama sisa umur token itu sendiri, biar entry di Redis
    otomatis ilang begitu token-nya expired secara natural.
    Kalau Redis lagi down, gagal dengan log warning (bukan crash) — logout
    tetap dianggap berhasil dari sisi user, meski proteksinya sementara
    gak aktif sampai Redis nyala lagi.
    """
    if expires_in_seconds <= 0:
        return
    try:
        redis_client.set(_key(jti), "1", ex=expires_in_seconds)
    except Exception as exc:
        logger.warning(f"Gagal blocklist token di redis: {exc}")


def is_blocklisted(jti: str) -> bool:
    """Cek apakah token sudah di-blocklist.

    Kalau Redis lagi down, dianggap tidak di-blocklist (fail open) —
    lebih baik token tetap bisa dipakai daripada semua user ke-lock out.
    """
    try:
        return redis_client.exists(_key(jti)) == 1
    except Exception as exc:
        logger.warning(f"Gagal cek blocklist token di redis: {exc}")
        return False
