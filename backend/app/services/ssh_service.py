"""
SSH Service — logika koneksi SSH ke server remote.

Library yang digunakan: paramiko.
Jika paramiko belum terinstall, modul ini akan raise ImportError yang informatif
saat fungsi test_connection dipanggil (bukan saat import).
"""

from __future__ import annotations

import socket

from loguru import logger

from app.models.server import AuthType, Server, ServerStatus
from app.schemas.server import SSHTestResult

# Timeout default (detik) untuk percobaan koneksi SSH
_DEFAULT_TIMEOUT: int = 10


def test_connection(server: Server, timeout: int = _DEFAULT_TIMEOUT) -> SSHTestResult:
    """
    Coba buka koneksi SSH ke server.

    Mengembalikan SSHTestResult dengan success=True jika berhasil,
    atau success=False dengan pesan error jika gagal.

    Tipe kegagalan yang ditangani:
    - socket.timeout         → Connection timeout
    - ConnectionRefusedError → Port tidak terbuka / firewall
    - paramiko.AuthenticationException → Kredensial salah
    - paramiko.SSHException  → Error SSH lainnya (wrong key, dll)
    - Exception              → Fallback untuk error tidak terduga
    """
    try:
        import paramiko  # lazy import agar modul tetap bisa diimport tanpa paramiko
    except ImportError as exc:
        raise ImportError(
            "paramiko diperlukan untuk fitur SSH. Install dengan: uv add paramiko"
        ) from exc

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs: dict[str, object] = {
        "hostname": server.host,
        "port": server.port,
        "username": server.username,
        "timeout": timeout,
        "allow_agent": False,
        "look_for_keys": False,
    }

    if server.auth_type == AuthType.password:
        connect_kwargs["password"] = server.password
    else:
        # private_key berisi string isi key (bukan path file)
        import io
        pkey = paramiko.RSAKey.from_private_key(io.StringIO(server.private_key or ""))
        connect_kwargs["pkey"] = pkey

    try:
        client.connect(**connect_kwargs)  # type: ignore[arg-type]
        client.close()
        logger.info(f"SSH test OK: {server.host}:{server.port} (server_id={server.id})")
        return SSHTestResult(
            server_id=server.id,
            host=server.host,
            port=server.port,
            success=True,
            message="Connected",
        )

    except socket.timeout:
        msg = f"Connection timeout setelah {timeout} detik"
        logger.warning(f"SSH test FAILED [{server.host}:{server.port}]: {msg}")
        return SSHTestResult(
            server_id=server.id,
            host=server.host,
            port=server.port,
            success=False,
            message=msg,
        )

    except ConnectionRefusedError:
        msg = "Connection refused — port mungkin tertutup atau firewall memblokir"
        logger.warning(f"SSH test FAILED [{server.host}:{server.port}]: {msg}")
        return SSHTestResult(
            server_id=server.id,
            host=server.host,
            port=server.port,
            success=False,
            message=msg,
        )

    except Exception as exc:
        # AuthenticationException, SSHException, BadHostKeyException, dll
        module = type(exc).__module__
        if "paramiko" in module:
            msg = f"SSH error: {exc}"
        else:
            msg = f"Koneksi gagal: {exc}"
        logger.warning(f"SSH test FAILED [{server.host}:{server.port}]: {msg}")
        return SSHTestResult(
            server_id=server.id,
            host=server.host,
            port=server.port,
            success=False,
            message=msg,
        )

    finally:
        try:
            client.close()
        except Exception:
            pass


def resolve_new_status(result: SSHTestResult) -> ServerStatus:
    """Tentukan ServerStatus berdasarkan hasil tes SSH."""
    return ServerStatus.active if result.success else ServerStatus.error
