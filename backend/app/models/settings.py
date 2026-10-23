from enum import StrEnum

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel


class SyncMode(StrEnum):
    AUTO = "auto"  # el worker sincroniza solo cada `sync_interval_min`
    MANUAL = "manual"  # solo con el botón «Sincronizar ahora»


# Intervalos ofrecidos en Ajustes (minutos).
SYNC_INTERVALS = (15, 30, 60, 120, 360, 720, 1440)
DEFAULT_SYNC_INTERVAL = 30


class UserSettings(SQLModel, table=True):
    """Preferencias por usuario. Si no hay fila, se usan los valores por defecto."""

    __tablename__ = "user_settings"

    user_id: int = Field(foreign_key="user.id", primary_key=True, ondelete="CASCADE")
    sync_mode: SyncMode = Field(default=SyncMode.AUTO, sa_column=Column(String(16), nullable=False))
    sync_interval_min: int = DEFAULT_SYNC_INTERVAL
    weekly_goal_sessions: int = Field(default=3, ge=1, le=14)  # racha: semanas con al menos N entrenos
    # Enviar solas a Garmin las sesiones de los próximos 7 días (y sus cambios).
    garmin_workouts_auto: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
