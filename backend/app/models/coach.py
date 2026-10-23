from datetime import date, datetime

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_field


class CoachSettings(SQLModel, table=True):
    """Preferencias del entrenador IA: consentimiento para datos de salud, entrevista hecha y revisión semanal."""

    __tablename__ = "coach_settings"

    user_id: int = Field(foreign_key="user.id", primary_key=True, ondelete="CASCADE")
    health_consent: bool = False
    health_consent_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    interview_done_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    weekly_review: bool = Field(default=True, sa_column_kwargs={"server_default": "true"})


class CoachMemory(SQLModel, table=True):
    """
    Lo que el entrenador sabe de la persona más allá de los datos del reloj (lesiones, disponibilidad,
    preferencias…). Lo guarda la IA cuando la persona se lo cuenta o la propia persona; se puede ver,
    editar y borrar. Va en el contexto de la IA en cada conversación.
    """

    __tablename__ = "coach_memory"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    category: str = Field(max_length=16)
    content: str = Field(max_length=500)
    source: str = Field(default="ia", max_length=16)  # ia | usuario | entrevista | revision
    created_at: datetime = created_at_field()
    updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class WeeklyCheckin(SQLModel, table=True):
    """Revisión semanal: cómo se ha sentido la persona (respuestas) y el resumen del entrenador IA."""

    __tablename__ = "weekly_checkin"
    __table_args__ = (UniqueConstraint("user_id", "week_start"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    week_start: date  # lunes de la semana revisada
    status: str = Field(default="pending", max_length=16)  # pending | processing | done | error
    answers: dict = jsonb_field()
    summary: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    error: str = Field(default="", max_length=255)
    effects: list | None = jsonb_field(nullable=True)  # lo que guardó o propuso el entrenador al resumir
    created_at: datetime = created_at_field()
    updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class PlanProposal(SQLModel, table=True):
    """Cambio de una sesión del plan propuesto por la IA; solo se aplica si la persona lo acepta."""

    __tablename__ = "plan_proposal"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    planned_session_id: int = Field(foreign_key="planned_session.id", index=True, ondelete="CASCADE")
    change: dict = jsonb_field()  # {"day": "2026-10-30", "title": "…", "notes": "…", "blocks": [...]}
    reason: str = Field(max_length=500)
    status: str = Field(default="pending", max_length=16)  # pending | accepted | rejected | expired
    created_at: datetime = created_at_field()
    decided_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
