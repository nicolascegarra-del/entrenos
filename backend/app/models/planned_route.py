from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


def _json_list() -> Any:
    return Field(default_factory=list, sa_column=Column(JSONB, nullable=False, server_default=text("'[]'")))


class PlannedRoute(SQLModel, table=True):
    """
    Ruta dibujada en el mapa (inicio, puntos de paso y fin) y calculada por carreteras o senderos.
    Se guarda la traza ya calculada (`geometry`: [lat, lon, alt]) para no volver a pedirla.
    """

    __tablename__ = "planned_route"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    name: str = Field(max_length=120)
    mode: str = Field(max_length=16)  # asfalto | trail | bici | mtb
    waypoints: list = _json_list()  # [[lat, lon], …]
    geometry: list = _json_list()  # [[lat, lon, alt], …]
    profile: list = _json_list()  # [[distancia_m, alt], …]
    surfaces: list = _json_list()
    waytypes: list = _json_list()
    distance_m: int
    ascent_m: int
    descent_m: int
    estimated_s: int | None = None
    created_at: datetime = created_at_field()
    updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
