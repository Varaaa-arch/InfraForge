from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from fastapi import FastAPI
from loguru import logger

from app.api import health
from app.config import settings
from app.core.logging import setup_logging 
from app.database.session import check_database_connection
from app.database.redis_client import check_redis_connection

setup_logging(debug=settings.DEBUG)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting up {settings.APP_NAME} v{settings.APP_VERSION}...")
    check_database_connection()
    check_redis_connection()
    yield
    logger.info(f"Shutting down {settings.APP_NAME}")

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)
app.include_router(health.router)

@app.get("/")
def root () -> dict[str, str]:
    return {"message": f"Welcome to {settings.APP_NAME}!"}

