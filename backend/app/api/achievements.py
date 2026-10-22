"""Rachas, logros y retos del mes."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.models import UserSettings
from app.services import achievements as svc
from app.services.sync_schedule import get_user_settings

router = APIRouter(prefix="/achievements", tags=["logros"])


class WeeklyGoalIn(BaseModel):
    sessions: int = Field(ge=1, le=14, description="Entrenos por semana para mantener la racha")


@router.get("", summary="Racha, retos del mes, logros y próximos hitos")
def get_achievements(session: SessionDep, user: CurrentUser) -> dict:
    svc.evaluate(session, user.id, notify=False)  # la página siempre muestra lo último
    return svc.report(session, user.id)


@router.put("/weekly-goal", summary="Cambiar cuántos entrenos por semana cuentan para la racha")
def set_weekly_goal(body: WeeklyGoalIn, session: SessionDep, user: CurrentUser) -> dict:
    settings = session.get(UserSettings, user.id) or get_user_settings(session, user.id)
    settings.weekly_goal_sessions = body.sessions
    session.add(settings)
    session.commit()
    return svc.report(session, user.id)
