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
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.metrics import (
    ContainerBlockIOStats,
    ContainerMemoryStats,
    ContainerMetricsResponse,
    ContainerNetworkStats,
    ContainerTrendsResponse,
)
from app.schemas.response import ApiResponse
from app.services import container_service, container_trends_service, container_usage_service

router = APIRouter(prefix="/containers", tags=["containers"])


# ---------------------------------------------------------------------------
# Local schemas
# ---------------------------------------------------------------------------

class ContainerPortResponse(BaseModel):
    container_port: int
    protocol: str
    host_port: int | None = None
    host_ip: str | None = None


class ContainerResponse(BaseModel):
    id: str
    name: str
    image: str
    status: str
    created: str
    ports: list[ContainerPortResponse] = Field(default_factory=list)
    health: str | None = None
    compose_project: str | None = None
    compose_service: str | None = None
    restart_count: int = 0
    cpu_percent: float | None = None
    memory_usage_bytes: int | None = None
    memory_limit_bytes: int | None = None
    memory_percent: float | None = None


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
        usage_by_name = container_usage_service.collect_usage()

        items: list[ContainerResponse] = []
        for c in containers:
            usage = usage_by_name.get(c.name)
            items.append(
                ContainerResponse(
                    id=c.id,
                    name=c.name,
                    image=c.image,
                    status=c.status,
                    created=c.created,
                    ports=[
                        ContainerPortResponse(
                            container_port=port.container_port,
                            protocol=port.protocol,
                            host_port=port.host_port,
                            host_ip=port.host_ip,
                        )
                        for port in c.ports
                    ],
                    health=c.health,
                    compose_project=c.compose_project,
                    compose_service=c.compose_service,
                    restart_count=c.restart_count,
                    cpu_percent=usage.cpu_percent if usage else None,
                    memory_usage_bytes=usage.memory_usage_bytes if usage else None,
                    memory_limit_bytes=usage.memory_limit_bytes if usage else None,
                    memory_percent=usage.memory_percent if usage else None,
                )
            )
        return ApiResponse(data=items)
    except RuntimeError as exc:
        raise _handle_runtime(exc)


@router.get(
    "/usage/top",
    response_model=ApiResponse[ContainerTrendsResponse],
    summary="Tren top container (CPU/RAM)",
    description=(
        "Menampilkan container dengan pemakaian CPU tertinggi beserta tren CPU "
        "historis dari Prometheus. Metrik berasal dari exporter backend "
        "(`infraforge_container_cpu_percent` & `infraforge_container_memory_bytes`) "
        "yang di-scrape setiap 15 detik. Gunakan `?range=15m|1h|6h|24h`."
    ),
    responses={
        400: {"description": "Format range tidak valid"},
    },
)
def top_container_usage(
    range_value: str = Query(
        default="1h",
        alias="range",
        description="Rentang tren CPU (15m, 1h, 6h, 24h, maks 7d)",
    ),
    limit: int = Query(default=5, ge=1, le=20, description="Jumlah container teratas"),
    _: User = Depends(get_current_user),
) -> ApiResponse[ContainerTrendsResponse]:
    try:
        data = container_trends_service.collect(range_value, limit)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    return ApiResponse(data=data)


@router.get(
    "/{container_id}/metrics",
    response_model=ApiResponse[ContainerMetricsResponse],
    summary="Statistik resource container",
    description=(
        "Snapshot CPU dan RAM (plus network & block I/O) langsung dari Docker "
        "daemon via `container.stats(stream=False)`. Tidak bergantung pada cAdvisor."
    ),
    responses={
        404: {"description": "Container tidak ditemukan"},
        503: {"description": "Docker daemon tidak tersedia"},
    },
)
def get_container_metrics(
    container_id: str,
    _: User = Depends(get_current_user),
) -> ApiResponse[ContainerMetricsResponse]:
    try:
        stats = container_service.get_stats(container_id)
    except RuntimeError as exc:
        raise _handle_runtime(exc)

    return ApiResponse(
        data=ContainerMetricsResponse(
            container_id=stats.id,
            name=stats.name,
            image=stats.image,
            status=stats.status,
            cpu_percent=stats.cpu_percent,
            cpu_count=stats.cpu_count,
            memory=ContainerMemoryStats(
                usage_bytes=stats.memory_usage_bytes,
                limit_bytes=stats.memory_limit_bytes,
                percent=stats.memory_percent,
            ),
            network=ContainerNetworkStats(
                rx_bytes=stats.network_rx_bytes,
                tx_bytes=stats.network_tx_bytes,
            ),
            blkio=ContainerBlockIOStats(
                read_bytes=stats.blkio_read_bytes,
                write_bytes=stats.blkio_write_bytes,
            ),
            pids_current=stats.pids_current,
            sampled_at=stats.sampled_at,
        )
    )


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
