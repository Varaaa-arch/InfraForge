from fastapi import APIRouter, Response, status

from app.database.redis_client import check_redis_connection
from app.database.session import check_database_connection
from app.schemas.health import HealthStatus, ReadyStatus
from app.schemas.response import ApiResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthStatus])
def health() -> ApiResponse[HealthStatus]:
    return ApiResponse(data=HealthStatus(status="healthy"))


@router.get("/ready", response_model=ApiResponse[ReadyStatus])
def ready(response: Response) -> ApiResponse[ReadyStatus]:
    db_ok = check_database_connection()
    redis_ok = check_redis_connection()
    ready_ok = db_ok and redis_ok

    if not ready_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ApiResponse(
        success=ready_ok,
        data=ReadyStatus(
            status="ready" if ready_ok else "not ready",
            database="up" if db_ok else "down",
            redis="up" if redis_ok else "down",
        ),
    )
