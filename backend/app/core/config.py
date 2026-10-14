from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración leída de variables de entorno (ver `.env.example`)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "app-entrenos"
    app_env: str = "development"
    debug: bool = False

    database_url: str = "postgresql+psycopg://entrenos:entrenos@localhost:5432/entrenos"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    cors_origins: list[str] = ["http://localhost:3000"]

    storage_dir: str = "./data/storage"

    garmin_token_dir: str = "/data/garmin-tokens"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
