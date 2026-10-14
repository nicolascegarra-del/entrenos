from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Float, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_field, utcnow


class Device(SQLModel, table=True):
    """Reloj o sensor. Permite marcar en las gráficas cuándo cambiaste de dispositivo."""

    __table_args__ = (UniqueConstraint("user_id", "garmin_device_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # Los IDs de Garmin superan el rango de INTEGER (ej. 3 312 206 070).
    garmin_device_id: int = Field(sa_type=BigInteger)
    name: str = Field(max_length=120)
    first_seen: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    last_seen: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class Activity(SQLModel, table=True):
    """
    Actividad normalizada. Solo las métricas universales son columnas;
    todo lo demás (dependiente del reloj) va en `metrics`, con claves de `MetricDefinition`.
    """

    __table_args__ = (
        UniqueConstraint("user_id", "garmin_activity_id"),
        Index("ix_activity_user_start", "user_id", "start_time"),
        Index("ix_activity_user_sport_start", "user_id", "sport", "start_time"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    device_id: int | None = Field(default=None, foreign_key="device.id")
    garmin_activity_id: int | None = Field(default=None, sa_type=BigInteger)
    sport: str = Field(max_length=32)
    sub_sport: str | None = Field(default=None, max_length=64)
    name: str = Field(default="", max_length=255)
    start_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    timezone: str | None = Field(default=None, max_length=64)
    duration_s: float
    moving_duration_s: float | None = None
    distance_m: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_gain_m: float | None = None
    calories: float | None = None
    metrics: dict = jsonb_field()
    created_at: datetime = created_at_field()
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utcnow)
    )


class ActivityRaw(SQLModel, table=True):
    """
    Capa raw inmutable: lo que devolvió Garmin tal cual. Se puede reprocesar
    entera cuando el catálogo aprende métricas nuevas (`parser_version`).
    """

    __tablename__ = "activity_raw"

    activity_id: int = Field(foreign_key="activity.id", primary_key=True, ondelete="CASCADE")
    summary: dict = jsonb_field()
    splits: dict | None = jsonb_field(nullable=True)
    details: dict | None = jsonb_field(nullable=True)
    fit_object_key: str | None = Field(default=None, max_length=255)
    parser_version: int = 1
    fetched_at: datetime = created_at_field()


class ActivityStream(SQLModel, table=True):
    """
    Serie temporal de un canal (hr, speed, power, cadence, altitude, lat, lon...).
    Un sensor nuevo = un canal nuevo, sin cambios de esquema. El canal `time`
    guarda los segundos desde el inicio y alinea al resto por índice.
    """

    __tablename__ = "activity_stream"
    __table_args__ = (UniqueConstraint("activity_id", "channel"),)

    id: int | None = Field(default=None, primary_key=True)
    activity_id: int = Field(foreign_key="activity.id", index=True, ondelete="CASCADE")
    channel: str = Field(max_length=64)
    values: list[float | None] = Field(sa_column=Column(ARRAY(Float), nullable=False))


class Lap(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("activity_id", "index"),)

    id: int | None = Field(default=None, primary_key=True)
    activity_id: int = Field(foreign_key="activity.id", index=True, ondelete="CASCADE")
    index: int
    start_offset_s: float
    duration_s: float
    distance_m: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    avg_speed: float | None = None
    metrics: dict = jsonb_field()
