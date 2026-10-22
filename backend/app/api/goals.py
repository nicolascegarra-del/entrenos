from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.core.rate_limit import limiter
from app.models import Activity, RaceGoal
from app.services import progress as prog
from app.services import race_day
from app.services.forecast_explain import explain_paces
from app.services.limits import QuotaError, check_goal_quota
from app.services.plan_steps import local_day, sport_family
from app.services.race_forecast import forecast, full_report, goal_forecast, training_data, user_calibration
from app.services.race_models import riegel
from app.services.weather import WeatherError, geocode
from app.services.zones import effective_paces

router = APIRouter(prefix="/goals", tags=["objetivos"])

_NOT_FOUND = {404: {"description": "El objetivo no existe o no es tuyo."}}


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    race_date: date
    distance_m: float = Field(gt=0, le=250_000)
    target_time_s: float | None = Field(default=None, gt=0, le=7 * 24 * 3600)
    start_time: time | None = Field(default=None, description="Hora de salida (local)")
    location_name: str = Field(default="", max_length=160)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    elevation_gain_m: float | None = Field(default=None, ge=0, le=20000, description="Desnivel positivo (sin GPX)")


class CourseIn(BaseModel):
    gpx: str = Field(min_length=20, max_length=race_day.MAX_GPX_BYTES)
    name: str = Field(default="", max_length=120)


class GoalOut(GoalIn):
    id: int
    result_activity_id: int | None
    result_time_s: float | None
    predicted_time_s: float | None
    probable_s: float | None
    days_left: int
    has_course: bool = False


class ResultIn(BaseModel):
    activity_id: int


def _owned(session: SessionDep, user_id: int, goal_id: int) -> RaceGoal:
    goal = session.get(RaceGoal, goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Objetivo no encontrado.")
    return goal


def _out(session: SessionDep, goal: RaceGoal, with_forecast: bool = True) -> GoalOut:
    probable = goal_forecast(session, goal).probable_s if with_forecast else None
    return GoalOut(
        **goal.model_dump(include=set(GoalOut.model_fields) - {"probable_s", "days_left", "has_course"}),
        probable_s=probable,
        days_left=(goal.race_date - date.today()).days,
        has_course=bool(goal.course),
    )


@router.get(
    "/geocode",
    summary="Buscar el lugar de la carrera",
    description="Lugares que coinciden con el texto (Open-Meteo), para el clima del día de carrera.",
    responses={503: {"description": "Servicio de búsqueda no disponible"}},
)
@limiter.limit("30/minute")
def search_place(request: Request, user: CurrentUser, q: Annotated[str, Query(min_length=2, max_length=80)]) -> list:
    try:
        return geocode(q)
    except WeatherError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.get("", summary="Objetivos de carrera (próximos primero)")
def list_goals(session: SessionDep, user: CurrentUser) -> list[GoalOut]:
    goals = session.exec(select(RaceGoal).where(RaceGoal.user_id == user.id).order_by(RaceGoal.race_date)).all()
    today = date.today()
    upcoming = [g for g in goals if g.race_date >= today]
    past = sorted((g for g in goals if g.race_date < today), key=lambda g: g.race_date, reverse=True)
    return [_out(session, g) for g in upcoming + past]


@router.post(
    "",
    summary="Crear objetivo",
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Cuenta Básica: máximo de objetivos activos"}},
)
def create_goal(body: GoalIn, session: SessionDep, user: CurrentUser) -> GoalOut:
    try:
        check_goal_quota(session, user)
    except QuotaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    goal = RaceGoal(user_id=user.id, **body.model_dump())
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return _out(session, goal)


@router.put("/{goal_id}", summary="Editar objetivo", responses=_NOT_FOUND)
def update_goal(goal_id: int, body: GoalIn, session: SessionDep, user: CurrentUser) -> GoalOut:
    goal = _owned(session, user.id, goal_id)
    for key, value in body.model_dump().items():
        setattr(goal, key, value)
    goal.updated_at = datetime.now(UTC)
    session.add(goal)
    session.commit()
    return _out(session, goal)


@router.delete("/{goal_id}", summary="Borrar objetivo", status_code=204, responses=_NOT_FOUND)
def delete_goal(goal_id: int, session: SessionDep, user: CurrentUser) -> Response:
    session.delete(_owned(session, user.id, goal_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{goal_id}/report",
    summary="Previsión, evolución y preparación",
    description=(
        "Previsión con rango (Riegel personal + VDOT de Daniels + Tanda en maratón), avisos de fiabilidad, "
        "diferencia con el objetivo y VDOT necesario, evolución semanal, checklist y ritmos de Daniels."
    ),
    responses=_NOT_FOUND,
)
def goal_report(goal_id: int, session: SessionDep, user: CurrentUser) -> dict:
    goal = _owned(session, user.id, goal_id)
    report = full_report(session, goal)
    report_forecast = report["forecast"]
    report["forecast"] = asdict(report_forecast)
    report["goal"] = _out(session, goal, with_forecast=False)
    report["paces_explanation"] = explain_paces(report_forecast)
    return report


@router.get(
    "/{goal_id}/race-day",
    summary="Plan del día de carrera",
    description=(
        "Previsión ajustada por calor (temperatura + punto de rocío) y desnivel (Minetti 2002), clima de "
        "Open-Meteo, ritmo por km y avituallamiento."
    ),
    responses=_NOT_FOUND,
)
def race_day_plan(goal_id: int, session: SessionDep, user: CurrentUser) -> dict:
    return race_day.report(session, _owned(session, user.id, goal_id))


@router.put(
    "/{goal_id}/course",
    summary="Subir el GPX del recorrido",
    responses={**_NOT_FOUND, 422: {"description": "GPX no válido o sin altitudes"}},
)
def set_course(goal_id: int, body: CourseIn, session: SessionDep, user: CurrentUser) -> GoalOut:
    goal = _owned(session, user.id, goal_id)
    try:
        course = race_day.parse_gpx(body.gpx, body.name)
    except race_day.GpxError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    goal.course = course
    if goal.lat is None:  # sin lugar: el clima se toma en la salida del recorrido
        goal.lat, goal.lon = course["start"]
    goal.updated_at = datetime.now(UTC)
    session.add(goal)
    session.commit()
    return _out(session, goal)


@router.delete("/{goal_id}/course", summary="Quitar el GPX", status_code=204, responses=_NOT_FOUND)
def clear_course(goal_id: int, session: SessionDep, user: CurrentUser) -> Response:
    goal = _owned(session, user.id, goal_id)
    goal.course = None
    session.add(goal)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{goal_id}/candidates",
    summary="Actividades de carrera del día del objetivo (para marcar el resultado)",
    responses=_NOT_FOUND,
)
def result_candidates(goal_id: int, session: SessionDep, user: CurrentUser) -> list[dict]:
    goal = _owned(session, user.id, goal_id)
    activities = prog.user_activities(session, user.id, goal.race_date - timedelta(days=1))
    return [
        {"id": a.id, "name": a.name, "start_time": a.start_time, "distance_m": a.distance_m, "duration_s": a.duration_s}
        for a in activities
        if local_day(a.start_time, a.timezone) == goal.race_date and sport_family(a.sport) == "running"
    ]


@router.put(
    "/{goal_id}/result",
    summary="Marcar la carrera real (calibra las previsiones siguientes)",
    description=(
        "Guarda el tiempo real (ajustado a la distancia exacta del objetivo con Riegel si el GPS difiere) "
        "y la previsión del día anterior. La relación real/previsto corrige las previsiones futuras."
    ),
    responses={**_NOT_FOUND, 400: {"description": "La actividad no es tuya o no tiene distancia."}},
)
def set_result(goal_id: int, body: ResultIn, session: SessionDep, user: CurrentUser) -> GoalOut:
    goal = _owned(session, user.id, goal_id)
    activity = session.get(Activity, body.activity_id)
    if activity is None or activity.user_id != user.id or not activity.distance_m:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La actividad no existe, no es tuya o no tiene distancia.")
    race_day = local_day(activity.start_time, activity.timezone)
    activities = [
        a for a in prog.user_activities(session, user.id) if a.id != activity.id
    ]  # la propia carrera no puede influir en su previsión
    before = forecast(
        goal.distance_m,
        training_data(activities, race_day - timedelta(days=1)),
        user_calibration(session, user.id, exclude_goal=goal.id),
    )
    goal.result_activity_id = activity.id
    goal.result_time_s = round(riegel(activity.duration_s, activity.distance_m, goal.distance_m))
    goal.predicted_time_s = before.probable_s
    goal.updated_at = datetime.now(UTC)
    session.add(goal)
    session.commit()
    return _out(session, goal)


@router.delete("/{goal_id}/result", summary="Quitar el resultado", status_code=204, responses=_NOT_FOUND)
def clear_result(goal_id: int, session: SessionDep, user: CurrentUser) -> Response:
    goal = _owned(session, user.id, goal_id)
    goal.result_activity_id = goal.result_time_s = goal.predicted_time_s = None
    session.add(goal)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


paces_router = APIRouter(tags=["objetivos"])


@paces_router.get(
    "/training-paces",
    summary="Ritmos de entrenamiento de Daniels según tu VDOT actual",
    description="E (suave), M (maratón), T (umbral), I (intervalos) y R (repeticiones), en s/km.",
)
def training_paces(session: SessionDep, user: CurrentUser) -> dict:
    data = training_data(prog.user_activities(session, user.id), date.today())
    f = forecast(10000, data)
    eff = effective_paces(session, user.id)
    if eff is None:
        return {"vdot": None, "source": None, "paces": None, "explanation": None, "basis": None}
    return {
        "vdot": eff["vdot"],
        "source": f.vdot_source,
        "paces": eff["paces"],
        "explanation": explain_paces(f) if f.vdot_current else None,
        **{
            k: eff[k]
            for k in (
                "basis",
                "vdot_marks",
                "vdot_from_races",
                "vdot_threshold",
                "threshold_pace_s_km",
                "threshold_source",
                "alternatives",
            )
        },
    }
