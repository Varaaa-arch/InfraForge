from fastapi import APIRouter, Response, status

from app.database.session import check_database_connection 
from app.database.redis_client import check_redis_connection 

router = APIRouter(tags=["Health Check"])

@router.get("/health")
def health() -> dict:
    return {"status": "ok"}

@router.get("/ready")
def readiness_check(response: Response) -> dict:
    db_connected = check_database_connection() 
    redis_connected = check_redis_connection() 

    if not db_connected or not redis_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return {
        "status": "ready" if (db_connected and redis_connected) else "not ready",
        "database": "up" if db_connected else "down",
        "redis": "up" if redis_connected else "down"
    }

