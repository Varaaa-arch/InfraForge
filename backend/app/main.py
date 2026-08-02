from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.api import applications, auth, containers, dashboard, docker, env_vars, health, projects, servers, users
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
    {
        "name": "users",
        "description": "Manajemen profil user yang sedang login.",
    },
    {
        "name": "projects",
        "description": "Create, read, update, delete project milik user.",
    },
    {
        "name": "dashboard",
        "description": "Ringkasan statistik untuk user yang sedang login.",
    },
    {
        "name": "servers",
        "description": (
            "Manajemen server remote: tambah, list, update, hapus, "
            "dan tes koneksi SSH ke server target."
        ),
    },
    {
        "name": "env-vars",
        "description": (
            "Manajemen environment variables per project. "
            "Value dienkripsi otomatis dengan Fernet sebelum disimpan ke database."
        ),
    },
    {
        "name": "applications",
        "description": (
            "Manajemen aplikasi dalam project: daftarkan, konfigurasi deployment "
            "(branch, Dockerfile path, docker-compose path, build context), "
            "dan pantau status operasional aplikasi."
        ),
    },
    {
        "name": "docker",
        "description": (
            "Manajemen Docker Images: list image lokal, pull dari registry, "
            "dan hapus image."
        ),
    },
    {
        "name": "containers",
        "description": (
            "Manajemen Docker Containers: list, start, stop, restart, hapus, "
            "lihat log, dan inspect detail container."
        ),
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
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(dashboard.router)
app.include_router(servers.router)
app.include_router(env_vars.router)
app.include_router(applications.router)
app.include_router(docker.router)
app.include_router(containers.router)

@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok"}
