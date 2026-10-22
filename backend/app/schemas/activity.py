from datetime import datetime

from pydantic import BaseModel, field_validator


def numeric_metrics(value: object) -> object:
    """Solo las métricas numéricas: `metrics` también guarda cálculos internos (p. ej. la curva de ritmos)."""
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if isinstance(v, int | float) and not isinstance(v, bool)}
    return value


class ActivitySummary(BaseModel):
    id: int
    sport: str
    name: str
    start_time: datetime
    timezone: str | None
    duration_s: float
    distance_m: float | None
    avg_hr: float | None
    elevation_gain_m: float | None
    metrics: dict[str, float]
    gear_id: int | None = None

    _numeric = field_validator("metrics", mode="before")(numeric_metrics)


class ActivityPage(BaseModel):
    items: list[ActivitySummary]
    next_cursor: str | None


class LapRead(BaseModel):
    index: int
    start_offset_s: float
    duration_s: float
    distance_m: float | None
    avg_hr: float | None
    max_hr: float | None
    avg_speed: float | None
    metrics: dict[str, float]


class DeviceRead(BaseModel):
    id: int
    name: str


class ActivityDetail(ActivitySummary):
    moving_duration_s: float | None
    max_hr: float | None
    calories: float | None
    device: DeviceRead | None
    laps: list[LapRead]
    channels: list[str]
    manual: bool  # registrada a mano (sin Garmin): se puede borrar


class StreamsResponse(BaseModel):
    points: int
    channels: dict[str, list[float | None]]


class MetricDefinitionRead(BaseModel):
    key: str
    scope: str
    label: str
    unit: str
    higher_is_better: bool | None
    sports: list[str]


class SyncRunRead(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    new_activities: int
    daily_days: int
    error: str | None
