from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "InfraForge"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    SECRET_KEY: str 

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSGRES_DB: str = "infraforge"
    POSTGRES_USER: str = "infraforge"
    POSTGRES_PASSWORD: str = "infraforge"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    @property 
    def database_url(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSGRES_DB}"
        )

settings = Settings() # type: ignore[call-arg]


