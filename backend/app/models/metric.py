from enum import StrEnum

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import ARRAY, VARCHAR
from sqlmodel import Field, SQLModel

from app.models.base import jsonb_field


class MetricScope(StrEnum):
    ACTIVITY = "activity"  # valor agregado de una actividad (ej. cadencia media)
    STREAM = "stream"  # canal segundo a segundo (ej. potencia)
    DAILY = "daily"  # métrica diaria de salud (ej. HRV)


class MetricDefinition(SQLModel, table=True):
    """
    Catálogo de métricas conocidas.

    Es lo que permite cambiar de reloj sin migraciones: cada métrica nueva es una fila
    que dice de dónde se extrae (`sources`) y cómo se muestra. La UI solo pinta las
    métricas del catálogo que tienen datos.
    """

    __tablename__ = "metric_definition"

    key: str = Field(primary_key=True, max_length=64)
    scope: MetricScope = Field(sa_column=Column(String(16), nullable=False, index=True))
    label: str = Field(max_length=120)
    unit: str = Field(default="", max_length=32)
    # True: más es mejor (VO2max); False: menos es mejor (FC reposo); None: neutro.
    higher_is_better: bool | None = None
    sports: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(VARCHAR(32)), nullable=False))
    # Rutas de extracción por fuente, ej. {"garmin_summary": "avgPower", "fit_record": "power"}.
    sources: dict = jsonb_field()
