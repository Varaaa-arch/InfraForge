from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.api import auth, health
from app.config import settings
from app.core.exception_handler import register_exception_handlers
from app.core.logging import setup_logging
from app.database.redis_client import check_redis_connection
from app.database.session import check_database_connection
from app.middleware.logging_middleware import RequestLoggingMiddleware

setup_logging(debug=settings.DEBUG)

tags_metadata = [
    {
        "name": "health",
        "description": "Pengecekan kesehatan service (liveness/readiness).",
    },
    {
        "name": "auth",
        "description": "Registrasi, login, dan manajemen token JWT.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    check_database_connection()
    check_redis_connection()
    yield
    logger.info(f"Shutting down {settings.APP_NAME}")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API resmi InfraForge — platform DevOps self-hosted.",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
)

register_exception_handlers(app)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(health.router)
app.include_router(auth.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok"}
