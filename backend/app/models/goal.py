from datetime import date, datetime

from sqlalchemy import Column, DateTime, Index
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class RaceGoal(SQLModel, table=True):
    """
    Objetivo de carrera en asfalto. Al marcar la actividad de la carrera se guarda
    lo que predecía la app ese día: la diferencia calibra las previsiones siguientes.
    """

    __tablename__ = "race_goal"
    __table_args__ = (Index("ix_race_goal_user_date", "user_id", "race_date"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    name: str = Field(max_length=120)
    race_date: date
    distance_m: float = Field(gt=0)
    target_time_s: float | None = Field(default=None, gt=0)
    # Calibración (se rellena al marcar la carrera real).
    result_activity_id: int | None = Field(default=None, foreign_key="activity.id", ondelete="SET NULL")
    result_time_s: float | None = None
    predicted_time_s: float | None = None  # previsión «probable» del día anterior a la carrera
    created_at: datetime = created_at_field()
    updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
