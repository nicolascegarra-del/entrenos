from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.models import BlockKind, MatchMode
from app.schemas.activity import ActivitySummary

TargetMetric = Literal["pace", "speed", "hr", "power", "cadence"]


class BlockIn(BaseModel):
    kind: BlockKind
    repeat: int = Field(default=1, ge=1, le=50)
    duration_s: float | None = Field(default=None, gt=0, le=86400)
    distance_m: float | None = Field(default=None, gt=0, le=500_000)
    target_metric: TargetMetric | None = None
    target_min: float | None = Field(default=None, ge=0)
    target_max: float | None = Field(default=None, ge=0)
    recovery_duration_s: float | None = Field(default=None, gt=0, le=3600)
    recovery_distance_m: float | None = Field(default=None, gt=0, le=10_000)

    @model_validator(mode="after")
    def check_target(self) -> Self:
        if self.duration_s and self.distance_m:
            raise ValueError("Indica duración o distancia, no ambas.")
        if self.target_metric and self.target_min is None and self.target_max is None:
            raise ValueError("El objetivo necesita un mínimo, un máximo o ambos.")
        if self.target_min is not None and self.target_max is not None and self.target_min > self.target_max:
            raise ValueError("El mínimo del objetivo no puede ser mayor que el máximo.")
        return self


class BlockOut(BlockIn):
    position: int


class SessionIn(BaseModel):
    day: date
    sport: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    notes: str = Field(default="", max_length=2000)
    blocks: list[BlockIn] = Field(default_factory=list, max_length=30)


class SessionOut(BaseModel):
    id: int
    day: date
    sport: str
    title: str
    notes: str
    activity_id: int | None
    match_mode: MatchMode
    compliance_score: float | None
    plan_id: int | None = None  # generada por un plan de entrenamiento
    session_kind: str | None = None  # easy | long | threshold | intervals | race_pace | race
    planned_duration_s: float
    planned_distance_m: float | None
    blocks: list[BlockOut]


class SessionDetail(SessionOut):
    compliance_detail: dict
    activity: ActivitySummary | None


class MatchIn(BaseModel):
    mode: MatchMode
    activity_id: int | None = None
