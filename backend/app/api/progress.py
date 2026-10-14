from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models import Device, PlannedSession
from app.schemas.activity import ActivitySummary
from app.services import progress as svc
from app.services.insights import build_insights
from app.services.metric_catalog import CATALOG
from app.services.plan_steps import local_day, sport_family

router = APIRouter(tags=["progresión"])

Days = Annotated[int, Query(ge=7, le=3650, description="Días hacia atrás desde hoy")]


class FitnessPoint(BaseModel):
    day: date
    load: float
    ctl: float
    atl: float
    tsb: float


class FitnessResponse(BaseModel):
    lthr: float | None
    hr_rest: float
    points: list[FitnessPoint]


class WeekPoint(BaseModel):
    week: date
    distance_m: float
    duration_s: float
    count: int
    load: float


class SeriesPoint(BaseModel):
    day: date
    value: float


class EfficiencyPoint(BaseModel):
    day: date
    activity_id: int
    value: float


class RecordBest(BaseModel):
    time_s: float
    activity_id: int
    day: date


class RecordRead(BaseModel):
    key: str
    label: str
    distance_m: int
    best: RecordBest | None
    history: list[RecordBest]


class DeviceSpan(BaseModel):
    id: int
    name: str
    first_seen: date
    last_seen: date


class WeekTotals(BaseModel):
    distance_m: float
    duration_s: float
    count: int
    load: float


class PlannedBrief(BaseModel):
    id: int
    day: date
    title: str
    sport: str
    compliance_score: float | None
    activity_id: int | None


class SummaryResponse(BaseModel):
    this_week: WeekTotals
    last_week: WeekTotals
    fitness: FitnessPoint | None
    form_label: str | None
    vo2max: float | None
    resting_hr: float | None
    planned_this_week: list[PlannedBrief]
    compliance_avg: float | None
    recent: list[ActivitySummary]


def _since(days: int) -> date:
    return date.today() - timedelta(days=days)


@router.get(
    "/progress/fitness",
    summary="Carga, fitness (CTL), fatiga (ATL) y forma (TSB)",
    description="Carga hrTSS por actividad (FC media vs umbral y reposo); CTL/ATL con medias de 42/7 días.",
)
def fitness(session: SessionDep, user: CurrentUser, days: Days = 180) -> FitnessResponse:
    thresholds = svc.user_thresholds(session, user.id)
    per_day, _ = svc.loads_by_day(svc.user_activities(session, user.id), thresholds, svc.user_rpes(session, user.id))
    points = svc.fitness_series(per_day, _since(days), date.today())
    return FitnessResponse(lthr=thresholds.lthr, hr_rest=thresholds.hr_rest, points=points)


@router.get("/progress/weekly", summary="Volumen semanal")
def weekly(
    session: SessionDep,
    user: CurrentUser,
    weeks: Annotated[int, Query(ge=1, le=260)] = 26,
    sport: str | None = None,
) -> list[WeekPoint]:
    last = svc.week_start(date.today())
    first = last - timedelta(weeks=weeks - 1)
    activities = svc.user_activities(session, user.id, first)
    if sport:
        activities = [a for a in activities if sport_family(a.sport) == sport_family(sport)]
    _, per_activity = svc.loads_by_day(
        activities, svc.user_thresholds(session, user.id), svc.user_rpes(session, user.id)
    )
    return [WeekPoint(**w) for w in svc.weekly_volume(activities, per_activity, first, last)]


@router.get(
    "/progress/metric/{key}",
    summary="Serie de una métrica del catálogo",
    description="Diarias (resting_hr, hrv_last_night…) o de actividad (vo2max, avg_cadence…), una por día.",
    responses={404: {"description": "La métrica no está en el catálogo."}},
)
def metric(key: str, session: SessionDep, user: CurrentUser, days: Days = 180) -> list[SeriesPoint]:
    if not any(d.key == key for d in CATALOG):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Métrica desconocida.")
    return [SeriesPoint(**p) for p in svc.metric_series(session, user.id, key, _since(days))]


@router.get("/progress/efficiency", summary="Eficiencia aeróbica en carrera (m/min por pulsación)")
def efficiency(session: SessionDep, user: CurrentUser, days: Days = 365) -> list[EfficiencyPoint]:
    since = _since(days)
    points = []
    for a in svc.user_activities(session, user.id, since):
        value = svc.efficiency(a)
        day = local_day(a.start_time, a.timezone)
        if value is not None and day >= since:
            points.append(EfficiencyPoint(day=day, activity_id=a.id, value=value))
    return points


@router.get("/progress/records", summary="Mejores marcas en carrera y su evolución")
def records(session: SessionDep, user: CurrentUser) -> list[RecordRead]:
    return [RecordRead(**r) for r in svc.records(svc.user_activities(session, user.id))]


@router.get("/devices", summary="Dispositivos usados (para marcar cambios de reloj en las gráficas)")
def devices(session: SessionDep, user: CurrentUser) -> list[DeviceSpan]:
    rows = session.exec(select(Device).where(Device.user_id == user.id).order_by(Device.first_seen)).all()
    return [
        DeviceSpan(id=d.id, name=d.name, first_seen=d.first_seen.date(), last_seen=d.last_seen.date()) for d in rows
    ]


@router.get("/summary", summary="Resumen de la semana para la pantalla de inicio")
def summary(session: SessionDep, user: CurrentUser) -> SummaryResponse:
    today = date.today()
    this_monday = svc.week_start(today)
    last_monday = this_monday - timedelta(days=7)
    thresholds = svc.user_thresholds(session, user.id)
    activities = svc.user_activities(session, user.id)
    per_day, per_activity = svc.loads_by_day(activities, thresholds, svc.user_rpes(session, user.id))
    weeks = svc.weekly_volume(
        [a for a in activities if local_day(a.start_time, a.timezone) >= last_monday], per_activity, last_monday,
        this_monday,
    )  # fmt: skip
    totals = [WeekTotals(**{k: w[k] for k in ("distance_m", "duration_s", "count", "load")}) for w in weeks]
    series = svc.fitness_series(per_day, today, today)
    current = FitnessPoint(**series[-1]) if series else None

    planned = session.exec(
        select(PlannedSession)
        .where(
            PlannedSession.user_id == user.id,
            PlannedSession.day >= this_monday,
            PlannedSession.day < this_monday + timedelta(days=7),
        )  # fmt: skip
        .order_by(PlannedSession.day)
    ).all()
    scores = [p.compliance_score for p in planned if p.compliance_score is not None]

    def latest(key: str) -> float | None:
        points = svc.metric_series(session, user.id, key, today - timedelta(days=60))
        return points[-1]["value"] if points else None

    return SummaryResponse(
        this_week=totals[-1],
        last_week=totals[0],
        fitness=current,
        form_label=svc.form_label(current.tsb) if current else None,
        vo2max=latest("vo2max") or latest("vo2max_running"),
        resting_hr=latest("resting_hr"),
        planned_this_week=[PlannedBrief.model_validate(p, from_attributes=True) for p in planned],
        compliance_avg=round(sum(scores) / len(scores), 1) if scores else None,
        recent=[
            ActivitySummary.model_validate(a, from_attributes=True)
            for a in sorted(activities, key=lambda a: a.start_time, reverse=True)[:5]
        ],
    )


@router.get(
    "/progress/insights",
    summary="Análisis de la progresión con base científica",
    description=(
        "Estado general (carga, recuperación, constancia, tendencia aeróbica) y un análisis por sección con su "
        "estado, explicación dinámica y referencias. Incluye ACWR, distribución de intensidad, desacople, "
        "predicciones (Riegel) y ritmos (VDOT). Orientativo; no es consejo médico."
    ),
)
def insights(session: SessionDep, user: CurrentUser, days: Days = 180) -> dict:
    return build_insights(session, user.id, days)
