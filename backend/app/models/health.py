from datetime import date

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import jsonb_field


class DailyMetric(SQLModel, table=True):
    """Métricas diarias (FC reposo, HRV, sueño, Body Battery, VO2max...) con claves del catálogo."""

    __tablename__ = "daily_metric"
    __table_args__ = (UniqueConstraint("user_id", "day"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    day: date
    metrics: dict = jsonb_field()
    raw: dict = jsonb_field()


class AthleteZones(SQLModel, table=True):
    """Zonas y umbrales vigentes desde una fecha (FC, ritmo, potencia/FTP)."""

    __tablename__ = "athlete_zones"
    __table_args__ = (UniqueConstraint("user_id", "sport", "valid_from"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    sport: str = Field(max_length=32)
    valid_from: date
    # Ej. {"lthr": 172, "threshold_pace_s_km": 245, "ftp": 250}
    thresholds: dict = jsonb_field()
    # Ej. {"hr": [[0,140],[140,155],...], "pace": [...]}
    zones: dict = jsonb_field()
