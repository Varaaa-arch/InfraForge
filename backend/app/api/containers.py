"""
Router untuk manajemen Docker Containers (Task 3.5).

Endpoints:
  GET    /containers                        → List semua container
  POST   /containers/{id}/start             → Start container
  POST   /containers/{id}/stop              → Stop container
  POST   /containers/{id}/restart           → Restart container
  DELETE /containers/{id}                   → Hapus container
  GET    /containers/{id}/logs              → Log container
  GET    /containers/{id}/inspect           → Detail inspect container
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.response import ApiResponse
from app.services import container_service

router = APIRouter(prefix="/containers", tags=["containers"])


# ---------------------------------------------------------------------------
# Local schemas
# ---------------------------------------------------------------------------

class ContainerResponse(BaseModel):
    id: str
    name: str
    image: str
    status: str
    created: str


class LogsResponse(BaseModel):
    container_id: str
    logs: str


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _handle_runtime(exc: RuntimeError) -> HTTPException:
    """Map RuntimeError message ke HTTP status yang tepat."""
    msg = str(exc)
    if "tidak ditemukan" in msg.lower():
        return HTTPException(status.HTTP_404_NOT_FOUND, msg)
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, msg)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=ApiResponse[list[ContainerResponse]],
    summary="Daftar Docker containers",
    description=(
        "Menampilkan semua container di Docker daemon lokal. "
        "Default menampilkan semua status (running + stopped). "
        "Gunakan `?all=false` untuk hanya container yang running."
    ),
)
def list_containers(
    all: bool = Query(default=True, description="Tampilkan semua container termasuk yang stopped"),
    _: User = Depends(get_current_user),
) -> ApiResponse[list[ContainerResponse]]:
    try:
        containers = container_service.list_containers(all_containers=all)
        return ApiResponse(
            data=[
                ContainerResponse(
                    id=c.id,
                    name=c.name,
                    image=c.image,
                    status=c.status,
                    created=c.created,
                )
                for c in containers
            ]
        )
    except RuntimeError as exc:
        raise _handle_runtime(exc)


@router.post(
    "/{container_id}/start",
    response_model=ApiResponse[MessageResponse],
    summary="Start container",
    description="Menjalankan container yang sedang dalam state stopped atau paused.",
)
def start_container(
    container_id: str,
    _: User = Depends(get_current_user),
) -> ApiResponse[MessageResponse]:
    try:
        container_service.start_container(container_id)
        return ApiResponse(data=MessageResponse(message=f"Container {container_id} berhasil distart"))
    except RuntimeError as exc:
        raise _handle_runtime(exc)


@router.post(
    "/{container_id}/stop",
    response_model=ApiResponse[MessageResponse],
    summary="Stop container",
    description="Menghentikan container yang sedang running.",
)
def stop_container(
    container_id: str,
    timeout: int = Query(default=10, ge=1, description="Timeout stop dalam detik"),
    _: User = Depends(get_current_user),
) -> ApiResponse[MessageResponse]:
    try:
        container_service.stop_container(container_id, timeout=timeout)
        return ApiResponse(data=MessageResponse(message=f"Container {container_id} berhasil distop"))
    except RuntimeError as exc:
        raise _handle_runtime(exc)


@router.post(
    "/{container_id}/restart",
    response_model=ApiResponse[MessageResponse],
    summary="Restart container",
    description="Merestart container (stop + start).",
)
def restart_container(
    container_id: str,
    timeout: int = Query(default=10, ge=1, description="Timeout restart dalam detik"),
    _: User = Depends(get_current_user),
) -> ApiResponse[MessageResponse]:
    try:
        container_service.restart_container(container_id, timeout=timeout)
        return ApiResponse(data=MessageResponse(message=f"Container {container_id} berhasil direstart"))
    except RuntimeError as exc:
        raise _handle_runtime(exc)


@router.delete(
    "/{container_id}",
    response_model=ApiResponse[MessageResponse],
    summary="Hapus container",
    description=(
        "Menghapus container secara permanen. "
        "Gunakan `?force=true` untuk memaksa hapus container yang masih running."
    ),
)
def remove_container(
    container_id: str,
    force: bool = Query(default=False, description="Paksa hapus container yang running"),
    _: User = Depends(get_current_user),
) -> ApiResponse[MessageResponse]:
    try:
        container_service.remove_container(container_id, force=force)
        return ApiResponse(data=MessageResponse(message=f"Container {container_id} berhasil dihapus"))
    except RuntimeError as exc:
        raise _handle_runtime(exc)


@router.get(
    "/{container_id}/logs",
    response_model=ApiResponse[LogsResponse],
    summary="Log container",
    description=(
        "Menampilkan output log (stdout + stderr) dari container. "
        "Gunakan `?tail=N` untuk membatasi jumlah baris. "
        "Gunakan `?timestamps=true` untuk menyertakan timestamp."
    ),
)
def get_logs(
    container_id: str,
    tail: int = Query(default=100, ge=1, le=10000, description="Jumlah baris log terakhir"),
    timestamps: bool = Query(default=False, description="Sertakan timestamp di tiap baris"),
    _: User = Depends(get_current_user),
) -> ApiResponse[LogsResponse]:
    try:
        logs = container_service.get_logs(container_id, tail=tail, timestamps=timestamps)
        return ApiResponse(data=LogsResponse(container_id=container_id, logs=logs))
    except RuntimeError as exc:
        raise _handle_runtime(exc)


@router.get(
    "/{container_id}/inspect",
    response_model=ApiResponse[dict[str, Any]],
    summary="Inspect container",
    description=(
        "Menampilkan detail lengkap container dalam format JSON, "
        "setara dengan output `docker inspect <id>`."
    ),
)
def inspect_container(
    container_id: str,
    _: User = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    try:
        details = container_service.inspect_container(container_id)
        return ApiResponse(data=details)
    except RuntimeError as exc:
        raise _handle_runtime(exc)
