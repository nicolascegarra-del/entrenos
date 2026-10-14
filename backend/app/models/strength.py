from datetime import datetime

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import utcnow


class StrengthSet(SQLModel, table=True):
    """
    Serie de fuerza de una actividad. Se registran a mano porque muchos relojes
    (como el Forerunner 735XT) no guardan repeticiones ni pesos.
    """

    __tablename__ = "strength_set"
    __table_args__ = (UniqueConstraint("activity_id", "position"),)

    id: int | None = Field(default=None, primary_key=True)
    activity_id: int = Field(foreign_key="activity.id", index=True, ondelete="CASCADE")
    position: int
    exercise: str = Field(max_length=80, index=True)
    reps: int | None = Field(default=None, ge=0)
    weight_kg: float | None = Field(default=None, ge=0)
    duration_s: float | None = Field(default=None, ge=0)


class ActivityFeedback(SQLModel, table=True):
    """Sensaciones tras el entreno: esfuerzo percibido (RPE 1–10), cómo te sentiste (1–5) y notas."""

    __tablename__ = "activity_feedback"

    activity_id: int = Field(foreign_key="activity.id", primary_key=True, ondelete="CASCADE")
    rpe: int | None = Field(default=None, ge=1, le=10)
    feeling: int | None = Field(default=None, ge=1, le=5)
    notes: str = Field(default="", max_length=2000)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utcnow)
    )
