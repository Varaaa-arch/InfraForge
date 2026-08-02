"""
Container Service — manajemen Docker containers.

Operasi yang didukung:
- list: tampilkan semua container (running + stopped)
- start / stop / restart: kontrol lifecycle container
- remove: hapus container
- logs: ambil stdout/stderr container
- inspect: detail lengkap container (raw attrs dari Docker daemon)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# Re-use client factory dari docker_service
# ---------------------------------------------------------------------------

def _get_client() -> Any:
    try:
        import docker
        import docker.errors  # noqa: F401
    except ImportError as exc:
        raise ImportError("docker-py diperlukan. Install dengan: uv add docker") from exc
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as exc:
        raise RuntimeError(f"Tidak dapat terhubung ke Docker daemon: {exc}") from exc


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ContainerInfo:
    id: str          # 12-char short ID
    name: str
    image: str
    status: str      # running, exited, paused, etc.
    created: str


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def list_containers(all_containers: bool = True) -> list[ContainerInfo]:
    """
    Daftar semua container.

    Args:
        all_containers: True = tampilkan juga yang sudah stop.
                        False = hanya yang sedang running.
    """
    client = _get_client()
    try:
        containers = client.containers.list(all=all_containers)
        result: list[ContainerInfo] = []
        for c in containers:
            result.append(
                ContainerInfo(
                    id=c.short_id,
                    name=c.name,
                    image=c.image.tags[0] if c.image.tags else c.image.short_id,
                    status=c.status,
                    created=c.attrs.get("Created", ""),
                )
            )
        return result
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil daftar container: {exc}") from exc


def _get_container(client: Any, container_id: str) -> Any:
    """Ambil container object. Raise RuntimeError jika tidak ditemukan."""
    import docker.errors

    try:
        return client.containers.get(container_id)
    except docker.errors.NotFound:
        raise RuntimeError(f"Container tidak ditemukan: {container_id}")
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil container {container_id}: {exc}") from exc


def start_container(container_id: str) -> None:
    """Start container yang sedang stopped/paused."""
    client = _get_client()
    container = _get_container(client, container_id)
    try:
        container.start()
        logger.info(f"Container {container_id} started")
    except Exception as exc:
        raise RuntimeError(f"Gagal start container {container_id}: {exc}") from exc


def stop_container(container_id: str, timeout: int = 10) -> None:
    """Stop container yang sedang running. Timeout dalam detik."""
    client = _get_client()
    container = _get_container(client, container_id)
    try:
        container.stop(timeout=timeout)
        logger.info(f"Container {container_id} stopped")
    except Exception as exc:
        raise RuntimeError(f"Gagal stop container {container_id}: {exc}") from exc


def restart_container(container_id: str, timeout: int = 10) -> None:
    """Restart container."""
    client = _get_client()
    container = _get_container(client, container_id)
    try:
        container.restart(timeout=timeout)
        logger.info(f"Container {container_id} restarted")
    except Exception as exc:
        raise RuntimeError(f"Gagal restart container {container_id}: {exc}") from exc


def remove_container(container_id: str, force: bool = False) -> None:
    """
    Hapus container.

    Args:
        force: Paksa hapus meski container sedang running.
    """
    client = _get_client()
    container = _get_container(client, container_id)
    try:
        container.remove(force=force)
        logger.info(f"Container {container_id} removed")
    except Exception as exc:
        raise RuntimeError(f"Gagal menghapus container {container_id}: {exc}") from exc


def get_logs(
    container_id: str,
    tail: int = 100,
    timestamps: bool = False,
) -> str:
    """
    Ambil log container (stdout + stderr).

    Args:
        tail:       Jumlah baris terakhir yang dikembalikan.
        timestamps: Sertakan timestamp di setiap baris log.

    Returns:
        String log.
    """
    client = _get_client()
    container = _get_container(client, container_id)
    try:
        raw = container.logs(
            stdout=True,
            stderr=True,
            tail=tail,
            timestamps=timestamps,
        )
        return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil log container {container_id}: {exc}") from exc


def inspect_container(container_id: str) -> dict[str, Any]:
    """
    Kembalikan detail lengkap container dari Docker daemon.
    Output identik dengan `docker inspect <id>`.
    """
    client = _get_client()
    container = _get_container(client, container_id)
    return dict(container.attrs)  # type: ignore[return-value]
