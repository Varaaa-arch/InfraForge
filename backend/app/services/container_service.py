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
from datetime import UTC, datetime
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


@dataclass
class ContainerStats:
    """Snapshot statistik resource satu container (Docker stats, non-stream)."""

    id: str
    name: str
    image: str
    status: str
    cpu_percent: float | None
    cpu_count: int | None
    memory_usage_bytes: int
    memory_limit_bytes: int
    memory_percent: float | None
    network_rx_bytes: int
    network_tx_bytes: int
    blkio_read_bytes: int
    blkio_write_bytes: int
    pids_current: int | None
    sampled_at: datetime


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


def count_containers(all_containers: bool = True) -> int:
    """
    Hitung jumlah container pada Docker daemon lokal.

    Args:
        all_containers: True = hitung juga yang sudah stop.
    """
    return len(list_containers(all_containers=all_containers))


def get_stats(container_id: str) -> ContainerStats:
    """
    Ambil snapshot statistik CPU/RAM/network/block-I/O container.

    Memakai ``container.stats(stream=False)`` sehingga tidak bergantung pada
    cAdvisor (yang bisa gagal melihat container di host overlayfs tertentu).

    CPU percent dihitung dari selisih ``cpu_stats`` vs ``precpu_stats``:
    ``(Δcpu / Δsystem) × online_cpus × 100``.

    Memory percent mengikuti perilaku ``docker stats``: page cache
    (``inactive_file``/``cache``) dikurangkan dari ``usage``.
    """
    client = _get_client()
    container = _get_container(client, container_id)
    try:
        raw = container.stats(stream=False)
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil statistik container {container_id}: {exc}") from exc

    if not isinstance(raw, dict):
        raise RuntimeError(f"Format statistik container {container_id} tidak valid")

    cpu_stats = raw.get("cpu_stats") or {}
    precpu_stats = raw.get("precpu_stats") or {}
    cpu_usage = cpu_stats.get("cpu_usage") or {}
    pre_cpu_usage = precpu_stats.get("cpu_usage") or {}

    cpu_delta = int(cpu_usage.get("total_usage") or 0) - int(
        pre_cpu_usage.get("total_usage") or 0
    )
    system_delta = int(cpu_stats.get("system_cpu_usage") or 0) - int(
        precpu_stats.get("system_cpu_usage") or 0
    )
    cpu_count = cpu_stats.get("online_cpus") or len(cpu_usage.get("percpu_usage") or [])
    cpu_count = int(cpu_count) if cpu_count else None
    cpu_percent: float | None = None
    has_previous_sample = bool(pre_cpu_usage) and (
        precpu_stats.get("system_cpu_usage") is not None
    )
    if has_previous_sample and cpu_delta > 0 and system_delta > 0:
        cpu_percent = round((cpu_delta / system_delta) * (cpu_count or 1) * 100, 2)

    memory_stats = raw.get("memory_stats") or {}
    usage_bytes = int(memory_stats.get("usage") or 0)
    limit_bytes = int(memory_stats.get("limit") or 0)
    detail = memory_stats.get("stats") or {}
    cache_bytes = int(detail.get("inactive_file") or detail.get("cache") or 0)
    effective_usage = max(usage_bytes - cache_bytes, 0)
    memory_percent = (
        round(effective_usage / limit_bytes * 100, 2) if limit_bytes > 0 else None
    )

    networks = raw.get("networks") or {}
    network_rx_bytes = sum(
        int(iface.get("rx_bytes") or 0)
        for iface in networks.values()
        if isinstance(iface, dict)
    )
    network_tx_bytes = sum(
        int(iface.get("tx_bytes") or 0)
        for iface in networks.values()
        if isinstance(iface, dict)
    )

    io_entries = (raw.get("blkio_stats") or {}).get("io_service_bytes_recursive") or []
    blkio_read_bytes = 0
    blkio_write_bytes = 0
    for entry in io_entries:
        if not isinstance(entry, dict):
            continue
        value = int(entry.get("value") or 0)
        op = str(entry.get("op") or "").lower()
        if op == "read":
            blkio_read_bytes += value
        elif op == "write":
            blkio_write_bytes += value

    pids_current_raw = (raw.get("pids_stats") or {}).get("current")
    pids_current = int(pids_current_raw) if pids_current_raw is not None else None

    image = container.image.tags[0] if container.image.tags else container.image.short_id

    return ContainerStats(
        id=container.short_id,
        name=container.name,
        image=image,
        status=container.status,
        cpu_percent=cpu_percent,
        cpu_count=cpu_count,
        memory_usage_bytes=effective_usage,
        memory_limit_bytes=limit_bytes,
        memory_percent=memory_percent,
        network_rx_bytes=network_rx_bytes,
        network_tx_bytes=network_tx_bytes,
        blkio_read_bytes=blkio_read_bytes,
        blkio_write_bytes=blkio_write_bytes,
        pids_current=pids_current,
        sampled_at=datetime.now(tz=UTC),
    )


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
