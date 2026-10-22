from datetime import date, datetime

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class Gear(SQLModel, table=True):
    """
    Material (zapatillas) con sus kilómetros: los iniciales (si ya estaban usadas) más los de las
    actividades asignadas. Avisa al acercarse a `alert_km`. Puede venir de Garmin (`garmin_uuid`).
    """

    __tablename__ = "gear"
    __table_args__ = (UniqueConstraint("user_id", "garmin_uuid"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    name: str = Field(max_length=120)
    brand: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=80)
    sport: str = Field(default="running", max_length=32)
    start_km: float = Field(default=0, ge=0)
    alert_km: float = Field(default=700, gt=0)
    first_use: date | None = None  # desde cuándo se asignan solas las carreras (si es la de por defecto)
    is_default: bool = False
    retired: bool = False
    retired_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    garmin_uuid: str | None = Field(default=None, max_length=64)
    created_at: datetime = created_at_field()
