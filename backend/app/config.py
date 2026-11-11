from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "InfraForge"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str
    # Kunci enkripsi untuk Fernet (env var values). Jika tidak diset,
    # fallback ke SECRET_KEY. Format bebas — di-derive via SHA-256.
    ENCRYPTION_KEY: str | None = None

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "infraforge"
    POSTGRES_USER: str = "infraforge"
    POSTGRES_PASSWORD: str = "infraforge"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # ---------------------------------------------------------------------------
    # Loki (Centralized Logging)
    # ---------------------------------------------------------------------------
    # Base URL Loki HTTP API. Di dalam Docker Compose gunakan http://loki:3100.
    LOKI_URL: str = "http://localhost:3100"
    # Timeout request ke Loki (detik).
    LOKI_TIMEOUT: float = 10.0

    # ---------------------------------------------------------------------------
    # CORS
    # ---------------------------------------------------------------------------
    # Origin frontend yang diizinkan, pisahkan dengan koma.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Boleh di-override langsung via DATABASE_URL env var (berguna di CI).
    # Jika tidak diset, dibangun dari POSTGRES_* fields di bawah.
    DATABASE_URL: str | None = None

    # ---------------------------------------------------------------------------
    # GitHub Webhook
    # ---------------------------------------------------------------------------
    # Secret yang dikonfigurasi di Settings → Webhooks GitHub.
    # Wajib diset di production. Jika kosong string, endpoint webhook akan
    # menolak semua request dengan 500 (misconfiguration).
    GITHUB_WEBHOOK_SECRET: str = ""

    # ---------------------------------------------------------------------------
    # ARQ Worker (Async Redis Queue)
    # ---------------------------------------------------------------------------
    # Jumlah job yang bisa diproses worker secara bersamaan.
    ARQ_MAX_JOBS: int = 10
    # Timeout (detik) per job deployment sebelum worker men-cancel task.
    # Harus > timeout subprocess (600s × 2 perintah + overhead).
    ARQ_JOB_TIMEOUT: int = 1500
    # TTL key Redis untuk idempotency dedup X-GitHub-Delivery (detik).
    ARQ_DELIVERY_TTL: int = 86400  # 24 jam

    @property
    def db_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_dsn(self) -> str:
        """Redis DSN untuk ARQ worker (format: redis://host:port)."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS_ORIGINS (comma-separated) menjadi list origin."""
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]


settings = Settings()  # type: ignore[call-arg]
