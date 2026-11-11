"""
Router untuk Centralized Logging (Loki).

Endpoints:
  GET /logs              → Pencarian & filtering log (keyword, container, level)
  GET /logs/containers   → Daftar container yang memiliki stream log di Loki
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.log import LogContainersResponse, LogEntry, LogsResponse
from app.schemas.response import ApiResponse
from app.services import loki_service

router = APIRouter(prefix="/logs", tags=["logs"])


def _handle_error(exc: Exception) -> HTTPException:
    """ValueError → 400 (input tidak valid), lainnya → 503 (Loki bermasalah)."""
    if isinstance(exc, ValueError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.get(
    "",
    response_model=ApiResponse[LogsResponse],
    summary="Cari dan filter log",
    description=(
        "Mengambil log terpusat dari Loki. Filter yang didukung:\n"
        "- `q` → pencarian keyword di isi log.\n"
        "- `container` → nama container (exact match).\n"
        "- `level` → `error`, `warning`, `info`, `debug`, atau `all`.\n"
        "- `last` → rentang waktu ke belakang: `30m`, `1h`, `7d` (maks 7 hari).\n"
        "- `limit` → jumlah maksimum baris (1-1000)."
    ),
)
def search_logs(
    q: str | None = Query(
        default=None,
        max_length=200,
        description="Keyword yang dicari di dalam baris log",
    ),
    container: str | None = Query(
        default=None,
        max_length=128,
        description="Filter nama container (exact match)",
    ),
    level: str | None = Query(
        default=None,
        pattern="^(error|warning|info|debug|all)$",
        description="Filter level log",
    ),
    last: str = Query(
        default="1h",
        pattern=r"^\d+[smhd]$",
        description="Rentang waktu ke belakang (contoh: 30m, 1h, 7d)",
    ),
    limit: int = Query(default=200, ge=1, le=1000, description="Jumlah maksimum baris"),
    _: User = Depends(get_current_user),
) -> ApiResponse[LogsResponse]:
    try:
        result = loki_service.query_logs(
            container=container,
            level=level,
            keyword=q,
            last=last,
            limit=limit,
        )
    except (RuntimeError, ValueError) as exc:
        raise _handle_error(exc) from exc

    return ApiResponse(
        data=LogsResponse(
            query=result.query,
            count=len(result.entries),
            logs=[
                LogEntry(
                    timestamp=entry.timestamp,
                    timestamp_ns=entry.timestamp_ns,
                    line=entry.line,
                    level=entry.level,
                    container=entry.container,
                    stream=entry.stream,
                )
                for entry in result.entries
            ],
        )
    )


@router.get(
    "/containers",
    response_model=ApiResponse[LogContainersResponse],
    summary="Daftar container dengan log",
    description=(
        "Menampilkan nama-nama container yang memiliki stream log di Loki. "
        "Dipakai untuk mengisi dropdown filter container."
    ),
)
def list_log_containers(
    _: User = Depends(get_current_user),
) -> ApiResponse[LogContainersResponse]:
    try:
        containers = loki_service.list_containers()
    except RuntimeError as exc:
        raise _handle_error(exc) from exc

    return ApiResponse(
        data=LogContainersResponse(count=len(containers), containers=containers)
    )
