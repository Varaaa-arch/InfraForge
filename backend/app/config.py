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

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()  # type: ignore[call-arg]
