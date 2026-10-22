from datetime import date, datetime

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_field


class TrainingPlan(SQLModel, table=True):
    """
    Plan generado hacia un objetivo de carrera. Sus sesiones son `PlannedSession` con `plan_id`;
    cada semana se revisa y se adapta (ver services/training_plans.py).
    """

    __tablename__ = "training_plan"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    goal_id: int | None = Field(default=None, foreign_key="race_goal.id", ondelete="SET NULL")
    status: str = Field(default="active", sa_column=Column(String(16), nullable=False))  # active | cancelled | done
    start_date: date
    race_date: date
    distance_m: float
    weekdays: list = jsonb_field()  # días de entrenamiento (0 = lunes)
    long_run_weekday: int
    start_km_week: float
    vdot: float | None = None
    created_at: datetime = created_at_field()
    last_adapted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class TrainingPlanWeek(SQLModel, table=True):
    """Semana del plan: fase, volumen objetivo y, si se adaptó, la decisión y su motivo."""

    __tablename__ = "training_plan_week"

    id: int | None = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="training_plan.id", index=True, ondelete="CASCADE")
    index: int
    start_date: date
    phase: str = Field(max_length=16)  # base | build | peak | taper
    target_km: float
    is_recovery: bool = False
    adjustment: dict = jsonb_field()  # {"action": "hold", "reason": "...", "at": "..."}
