"""Planes de entrenamiento automáticos hacia un objetivo, con adaptación semanal."""

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator

from app.api.deps import CurrentUser, SessionDep
from app.models import RaceGoal, TrainingPlan
from app.services import training_plans as svc

router = APIRouter(prefix="/training-plans", tags=["planes de entrenamiento"])
_NOT_FOUND = {404: {"description": "No encontrado"}}


class PlanIn(BaseModel):
    goal_id: int
    weekdays: list[int] = Field(min_length=2, max_length=7, description="Días de entrenamiento (0 = lunes)")
    long_run_weekday: int = Field(ge=0, le=6)

    @field_validator("weekdays")
    @classmethod
    def valid_days(cls, value: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in value):
            raise ValueError("Los días van de 0 (lunes) a 6 (domingo).")
        return sorted(set(value))


def _goal(session: SessionDep, user_id: int, goal_id: int) -> RaceGoal:
    goal = session.get(RaceGoal, goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Objetivo no encontrado.")
    return goal


def _plan(session: SessionDep, user_id: int, plan_id: int) -> TrainingPlan:
    plan = session.get(TrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan no encontrado.")
    return plan


@router.post(
    "/preview",
    summary="Previsualizar un plan (sin guardarlo)",
    description="Fases, km por semana y sesiones del plan que se crearía para el objetivo.",
    responses={**_NOT_FOUND, 422: {"description": "Plan imposible (p. ej. faltan menos de 4 semanas)"}},
)
def preview(body: PlanIn, session: SessionDep, user: CurrentUser) -> dict:
    goal = _goal(session, user.id, body.goal_id)
    try:
        weeks = svc.preview(session, user, goal, body.weekdays, body.long_run_weekday)
    except svc.PlanError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return {
        "weeks": svc.preview_out(weeks),
        "start_km_week": svc.current_km_week(session, user.id, weeks[0].start),
    }


@router.post(
    "",
    summary="Crear el plan y añadir sus sesiones al calendario",
    description="Sustituye al plan activo (sus sesiones futuras sin hacer se borran).",
    status_code=status.HTTP_201_CREATED,
    responses={**_NOT_FOUND, 422: {"description": "Plan imposible"}},
)
def create(body: PlanIn, session: SessionDep, user: CurrentUser) -> dict:
    goal = _goal(session, user.id, body.goal_id)
    try:
        plan = svc.create(session, user, goal, body.weekdays, body.long_run_weekday)
    except svc.PlanError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return svc.report(session, plan)


@router.get("/active", summary="Plan activo con sus semanas y ajustes")
def active(session: SessionDep, user: CurrentUser) -> dict | None:
    plan = svc.active_plan(session, user.id)
    return svc.report(session, plan) if plan else None


@router.post(
    "/{plan_id}/adapt",
    summary="Revisar el plan ahora",
    description="Ajusta la semana en curso según la anterior (cumplimiento) y cómo llegas (frescura y carga).",
    responses=_NOT_FOUND,
)
def adapt(plan_id: int, session: SessionDep, user: CurrentUser) -> dict:
    plan = _plan(session, user.id, plan_id)
    if plan.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Este plan ya no está activo.")
    result = svc.adapt(session, plan)
    return {"adjustment": result, "plan": svc.report(session, plan)}


@router.delete("/{plan_id}", summary="Cancelar el plan (borra sus sesiones futuras)", status_code=204,
               responses=_NOT_FOUND)  # fmt: skip
def cancel(plan_id: int, session: SessionDep, user: CurrentUser) -> Response:
    svc.cancel(session, _plan(session, user.id, plan_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
