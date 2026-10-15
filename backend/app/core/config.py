from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración leída de variables de entorno (ver `.env.example`)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "app-entrenos"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://entrenos:entrenos@localhost:5432/entrenos"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    cors_origins: list[str] = ["http://localhost:3000"]

    storage_dir: str = "./data/storage"

    garmin_token_dir: str = "/data/garmin-tokens"  # solo para migrar tokens antiguos (en fichero) a la BD
    # Clave Fernet para cifrar los tokens de Garmin en la BD. Generar con:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    garmin_token_key: str = ""
    # Clave Fernet genérica para secretos en BD (Garmin y claves de IA). Si falta, se usa GARMIN_TOKEN_KEY,
    # así que las instalaciones existentes no tienen que cambiar nada.
    secrets_key: str = ""

    # Asistente IA: mensajes por usuario y día (protege el saldo de cada clave).
    chat_daily_limit: int = 100

    @property
    def fernet_key(self) -> str:
        return self.secrets_key or self.garmin_token_key

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
