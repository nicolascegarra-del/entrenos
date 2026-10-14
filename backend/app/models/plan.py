from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Column, Index, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_field


class BlockKind(StrEnum):
    WARMUP = "warmup"
    STEADY = "steady"
    INTERVAL = "interval"
    RECOVERY = "recovery"
    COOLDOWN = "cooldown"


class MatchMode(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class PlannedSession(SQLModel, table=True):
    """Sesión planificada; se empareja con la `Activity` real para calcular el cumplimiento."""

    __tablename__ = "planned_session"
    __table_args__ = (Index("ix_planned_session_user_day", "user_id", "day"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    day: date
    sport: str = Field(max_length=32)
    title: str = Field(max_length=255)
    notes: str = ""
    activity_id: int | None = Field(default=None, foreign_key="activity.id", index=True, ondelete="SET NULL")
    match_mode: MatchMode = Field(default=MatchMode.AUTO, sa_column=Column(String(16), nullable=False))
    compliance_score: float | None = None
    compliance_detail: dict = jsonb_field()
    created_at: datetime = created_at_field()


class PlannedBlock(SQLModel, table=True):
    """
    Bloque de la sesión, ej. 6 x 1000 m @ ritmo 3:55-4:05 /km con 90 s de recuperación.

    `target_metric`: pace (s/km), speed (km/h), hr (ppm), power (W) o cadence (ppm).
    La recuperación se intercala entre repeticiones (no tras la última).
    """

    __tablename__ = "planned_block"
    __table_args__ = (UniqueConstraint("session_id", "position"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="planned_session.id", index=True, ondelete="CASCADE")
    position: int
    kind: BlockKind = Field(sa_column=Column(String(16), nullable=False))
    repeat: int = Field(default=1, ge=1)
    duration_s: float | None = None
    distance_m: float | None = None
    target_metric: str | None = Field(default=None, max_length=64)
    target_min: float | None = None
    target_max: float | None = None
    recovery_duration_s: float | None = None
    recovery_distance_m: float | None = None
