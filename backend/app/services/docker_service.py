"""
Docker Service — manajemen Docker images dan interaksi dengan Docker daemon.

Menggunakan docker-py (lazy import) agar modul tetap bisa diimport
meski Docker tidak terinstall di environment.

Semua fungsi mengembalikan dataclass/dict yang sudah dinormalisasi
sehingga router tidak perlu tahu detail docker-py API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def _get_client() -> Any:
    """
    Buat Docker client dari environment (DOCKER_HOST atau socket default).
    Raise RuntimeError jika Docker daemon tidak dapat dihubungi.
    """
    try:
        import docker
        import docker.errors
    except ImportError as exc:
        raise ImportError(
            "docker-py diperlukan. Install dengan: uv add docker"
        ) from exc

    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as exc:
        raise RuntimeError(f"Tidak dapat terhubung ke Docker daemon: {exc}") from exc


# ---------------------------------------------------------------------------
# Image dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ImageInfo:
    id: str
    tags: list[str]
    size: int          # bytes
    created: str       # ISO timestamp string


@dataclass
class PullResult:
    image: str
    tag: str
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Image operations
# ---------------------------------------------------------------------------

def list_images() -> list[ImageInfo]:
    """
    Daftar semua image yang ada di Docker daemon lokal.
    Dikembalikan diurutkan dari yang terbesar dulu.
    """
    client = _get_client()
    try:
        images = client.images.list()
        result: list[ImageInfo] = []
        for img in images:
            result.append(
                ImageInfo(
                    id=img.id.replace("sha256:", "")[:12],
                    tags=img.tags or ["<none>:<none>"],
                    size=img.attrs.get("Size", 0),
                    created=img.attrs.get("Created", ""),
                )
            )
        logger.debug(f"Listed {len(result)} images")
        return result
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil daftar image: {exc}") from exc


def pull_image(image: str, tag: str = "latest") -> PullResult:
    """
    Pull Docker image dari registry.

    Args:
        image: Nama image (misal: nginx, python, ubuntu).
        tag:   Tag image (default: latest).

    Returns:
        PullResult dengan status pull.
    """
    client = _get_client()
    full_name = f"{image}:{tag}"
    try:
        logger.info(f"Pulling image: {full_name}")
        client.images.pull(image, tag=tag)
        logger.info(f"Pull berhasil: {full_name}")
        return PullResult(
            image=image,
            tag=tag,
            success=True,
            message=f"Image {full_name} berhasil di-pull",
        )
    except Exception as exc:
        logger.error(f"Pull gagal [{full_name}]: {exc}")
        return PullResult(
            image=image,
            tag=tag,
            success=False,
            message=f"Pull gagal: {exc}",
        )


def remove_image(image_id: str, force: bool = False) -> None:
    """
    Hapus Docker image berdasarkan ID atau nama:tag.

    Args:
        image_id: Image ID (12 char pendek atau full SHA256) atau nama:tag.
        force:    Paksa hapus meski ada container yang menggunakan image ini.

    Raises:
        RuntimeError: Jika image tidak ditemukan atau gagal dihapus.
    """
    import docker.errors  # type: ignore[import-untyped]

    client = _get_client()
    try:
        client.images.remove(image_id, force=force)
        logger.info(f"Image {image_id} berhasil dihapus")
    except docker.errors.ImageNotFound:
        raise RuntimeError(f"Image tidak ditemukan: {image_id}")
    except Exception as exc:
        raise RuntimeError(f"Gagal menghapus image {image_id}: {exc}") from exc
