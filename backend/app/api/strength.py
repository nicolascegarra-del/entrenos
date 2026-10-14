from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, delete, select

from app.api.deps import CurrentUser, SessionDep
from app.models import Activity, ActivityFeedback, DailyMetric, StrengthSet
from app.schemas.activity import ActivitySummary
from app.services.plan_service import match_pending
from app.services.plan_steps import local_day
from app.services.strength import (
    clean_exercise,
    estimated_1rm,
    exercise_history,
    exercise_key,
    exercise_overview,
    summarize_sets,
)

router = APIRouter(tags=["fuerza y sensaciones"])

_NOT_FOUND = {404: {"description": "La actividad no existe o no es tuya."}}
# Métricas de la noche/día de la actividad que se muestran junto a las sensaciones.
_CONTEXT_KEYS = ("sleep_seconds", "sleep_score", "resting_hr", "hrv_last_night", "body_battery_max")


def _owned(session: Session, user_id: int, activity_id: int) -> Activity:
    activity = session.get(Activity, activity_id)
    if activity is None or activity.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Actividad no encontrada.")
    return activity


# ─── Actividades manuales ────────────────────────────────────────────────────


class ManualActivityIn(BaseModel):
    sport: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=255)
    start_time: datetime = Field(description="Con zona horaria, ej. 2026-10-14T19:30:00+02:00")
    duration_s: float = Field(gt=0, le=86400)
    distance_m: float | None = Field(default=None, gt=0, le=500_000)

    @field_validator("start_time")
    @classmethod
    def needs_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("La hora de inicio debe incluir la zona horaria.")
        return value


@router.post(
    "/activities",
    summary="Registrar un entreno a mano",
    description="Para sesiones sin reloj (p. ej. gimnasio). Se empareja con el plan si hay sesión ese día.",
    status_code=status.HTTP_201_CREATED,
)
def create_manual_activity(body: ManualActivityIn, session: SessionDep, user: CurrentUser) -> ActivitySummary:
    offset = body.start_time.utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset else 0
    sign = "+" if minutes >= 0 else "-"
    activity = Activity(
        user_id=user.id,
        sport=body.sport,
        name=body.name.strip(),
        start_time=body.start_time.astimezone(UTC),
        timezone=f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}",
        duration_s=body.duration_s,
        moving_duration_s=body.duration_s,
        distance_m=body.distance_m,
    )
    session.add(activity)
    session.commit()
    match_pending(session, user.id)
    session.refresh(activity)
    return ActivitySummary.model_validate(activity, from_attributes=True)


@router.delete(
    "/activities/{activity_id}",
    summary="Borrar un entreno registrado a mano",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_NOT_FOUND, 409: {"description": "Las actividades de Garmin no se borran desde la app."}},
)
def delete_manual_activity(activity_id: int, session: SessionDep, user: CurrentUser) -> Response:
    activity = _owned(session, user.id, activity_id)
    if activity.garmin_activity_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Las actividades de Garmin no se pueden borrar desde aquí.")
    session.delete(activity)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Series de fuerza ────────────────────────────────────────────────────────


class SetIn(BaseModel):
    exercise: str = Field(min_length=1, max_length=80)
    reps: int | None = Field(default=None, ge=0, le=500)
    weight_kg: float | None = Field(default=None, ge=0, le=1000)
    duration_s: float | None = Field(default=None, ge=0, le=3600)


class SetOut(SetIn):
    position: int
    e1rm_kg: float | None


class SetsResponse(BaseModel):
    sets: list[SetOut]
    summary: list[dict]


def _sets_response(sets: list[StrengthSet]) -> SetsResponse:
    return SetsResponse(
        sets=[
            SetOut(
                **s.model_dump(include={"position", "exercise", "reps", "weight_kg", "duration_s"}),
                e1rm_kg=estimated_1rm(s.weight_kg, s.reps),
            )  # fmt: skip
            for s in sorted(sets, key=lambda s: s.position)
        ],
        summary=summarize_sets(sets),
    )


@router.get("/activities/{activity_id}/sets", summary="Series de fuerza", responses=_NOT_FOUND)
def get_sets(activity_id: int, session: SessionDep, user: CurrentUser) -> SetsResponse:
    _owned(session, user.id, activity_id)
    return _sets_response(list(session.exec(select(StrengthSet).where(StrengthSet.activity_id == activity_id))))


@router.put(
    "/activities/{activity_id}/sets",
    summary="Guardar las series (reemplaza todas)",
    description="Incluye 1RM estimado por serie (Epley, hasta 12 repeticiones) y resumen por ejercicio.",
    responses=_NOT_FOUND,
)
def put_sets(activity_id: int, body: list[SetIn], session: SessionDep, user: CurrentUser) -> SetsResponse:
    _owned(session, user.id, activity_id)
    if len(body) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Máximo 200 series por actividad.")
    session.exec(delete(StrengthSet).where(StrengthSet.activity_id == activity_id))
    sets = [
        StrengthSet(activity_id=activity_id, position=i, **(s.model_dump() | {"exercise": clean_exercise(s.exercise)}))
        for i, s in enumerate(body)
    ]
    session.add_all(sets)
    session.commit()
    return _sets_response(sets)


# ─── Sensaciones (RPE) ───────────────────────────────────────────────────────


class FeedbackIn(BaseModel):
    rpe: int | None = Field(default=None, ge=1, le=10)
    feeling: int | None = Field(default=None, ge=1, le=5)
    notes: str = Field(default="", max_length=2000)


class FeedbackOut(FeedbackIn):
    day: date
    context: dict[str, float]


def _feedback_out(session: Session, activity: Activity) -> FeedbackOut:
    feedback = session.get(ActivityFeedback, activity.id) or ActivityFeedback(activity_id=activity.id)
    day = local_day(activity.start_time, activity.timezone)
    daily = session.exec(
        select(DailyMetric).where(DailyMetric.user_id == activity.user_id, DailyMetric.day == day)
    ).first()
    context = {k: daily.metrics[k] for k in _CONTEXT_KEYS if daily and daily.metrics.get(k) is not None}
    return FeedbackOut(rpe=feedback.rpe, feeling=feedback.feeling, notes=feedback.notes, day=day, context=context)


@router.get(
    "/activities/{activity_id}/feedback",
    summary="Sensaciones del entreno",
    description="RPE, sensación y notas, más el contexto del día (sueño, FC reposo, HRV, Body Battery).",
    responses=_NOT_FOUND,
)
def get_feedback(activity_id: int, session: SessionDep, user: CurrentUser) -> FeedbackOut:
    return _feedback_out(session, _owned(session, user.id, activity_id))


@router.put("/activities/{activity_id}/feedback", summary="Guardar sensaciones", responses=_NOT_FOUND)
def put_feedback(activity_id: int, body: FeedbackIn, session: SessionDep, user: CurrentUser) -> FeedbackOut:
    activity = _owned(session, user.id, activity_id)
    feedback = session.get(ActivityFeedback, activity_id) or ActivityFeedback(activity_id=activity_id)
    feedback.rpe, feedback.feeling, feedback.notes = body.rpe, body.feeling, body.notes.strip()
    session.add(feedback)
    session.commit()
    return _feedback_out(session, activity)


# ─── Progresión de fuerza ────────────────────────────────────────────────────


class ExerciseOverview(BaseModel):
    key: str
    exercise: str
    sessions: int
    last_day: date
    best_e1rm_kg: float | None
    e1rm_change_kg: float | None
    last_top_weight_kg: float | None


class ExerciseSession(BaseModel):
    day: date
    activity_id: int
    exercise: str
    sets: int
    reps: int
    volume_kg: float
    top_weight_kg: float | None
    best_e1rm_kg: float | None


@router.get("/strength/exercises", summary="Ejercicios registrados con su mejor 1RM estimado")
def list_exercises(session: SessionDep, user: CurrentUser) -> list[ExerciseOverview]:
    return [ExerciseOverview(**e) for e in exercise_overview(exercise_history(session, user.id))]


@router.get(
    "/strength/exercises/{name}",
    summary="Historial de un ejercicio por sesión",
    responses={404: {"description": "No hay series de ese ejercicio."}},
)
def exercise_detail(name: str, session: SessionDep, user: CurrentUser) -> list[ExerciseSession]:
    sessions = exercise_history(session, user.id).get(exercise_key(name))
    if not sessions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay series de ese ejercicio.")
    return [ExerciseSession(**s) for s in sessions]
