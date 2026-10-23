from datetime import date, datetime

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_field


class PerformanceTest(SQLModel, table=True):
    """
    Test de rendimiento (umbral, VO2max, FC máx…): metido a mano o detectado en una actividad
    (marcada como test o emparejada con una sesión de test del plan). Solo los confirmados cuentan
    para las zonas, y durante `TEST_VALID_DAYS` mandan sobre Garmin y las estimaciones.
    """

    __tablename__ = "performance_test"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    sport: str = Field(max_length=32)  # running | cycling | swimming
    protocol: str = Field(max_length=32)
    test_date: date
    activity_id: int | None = Field(default=None, foreign_key="activity.id", index=True, ondelete="SET NULL")
    planned_session_id: int | None = Field(
        default=None, foreign_key="planned_session.id", index=True, ondelete="SET NULL"
    )
    source: str = Field(default="manual", max_length=16)  # manual | activity | planned
    status: str = Field(default="detected", max_length=16)  # detected | confirmed | failed
    confidence: str = Field(default="", max_length=8)  # alta | media | baja
    # Ej. {"lthr": 172, "threshold_pace_s_km": 245, "vo2max": 55.1, "hr_max": 192}
    results: dict = jsonb_field()
    # Comprobaciones de calidad: [{"key": "regularidad", "ok": false, "message": "…"}]
    checks: list = Field(default_factory=list, sa_column=Column(JSONB, nullable=False, server_default="[]"))
    notes: str = Field(default="", max_length=500)
    created_at: datetime = created_at_field()
    confirmed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
