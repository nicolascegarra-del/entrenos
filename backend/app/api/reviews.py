"""Análisis de la IA de cada entreno: verlo, pedirlo o regenerarlo, y sus ajustes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep, require_module
from app.core.rate_limit import limiter
from app.models import Activity, ActivityReview
from app.models.ai import REVIEW_SPORTS
from app.services import activity_review as svc
from app.services.plan_steps import local_day

router = APIRouter(tags=["análisis de entrenos"], dependencies=[Depends(require_module("ia"))])
_NOT_FOUND = {404: {"description": "No encontrada"}}


class ReviewOut(BaseModel):
    activity_id: int
    status: str
    content: str
    error: str
    model_label: str | None
    tools: list[str] | None
    updated_at: datetime | None
    created_at: datetime


class LatestReviewOut(ReviewOut):
    activity_name: str
    activity_day: str


class ReviewSettingsIn(BaseModel):
    enabled: bool
    sports: list[str] = Field(default_factory=lambda: list(REVIEW_SPORTS))
    daily_max: int = Field(default=5, ge=1, le=20)

    @field_validator("sports")
    @classmethod
    def known(cls, value: list[str]) -> list[str]:
        bad = [s for s in value if s not in REVIEW_SPORTS]
        if bad:
            raise ValueError(f"Deportes no válidos: {', '.join(bad)}.")
        return list(dict.fromkeys(value))


class ReviewSettingsOut(ReviewSettingsIn):
    has_ai: bool = Field(description="Hay una IA configurada y activa")
    used_today: int


def _out(review: ActivityReview) -> ReviewOut:
    return ReviewOut(**review.model_dump(include=set(ReviewOut.model_fields) - {"model_label"}),
                     model_label=svc.provider_label(review))  # fmt: skip


def _owned_activity(session: SessionDep, user_id: int, activity_id: int) -> Activity:
    activity = session.get(Activity, activity_id)
    if activity is None or activity.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Actividad no encontrada.")
    return activity


def _settings_out(session: SessionDep, user_id: int) -> ReviewSettingsOut:
    s = svc.get_settings(session, user_id)
    return ReviewSettingsOut(enabled=s.enabled, sports=s.sports, daily_max=s.daily_max,
                             has_ai=svc.active_config(session, user_id) is not None,
                             used_today=svc.reviews_today(session, user_id))  # fmt: skip


@router.get("/activities/{activity_id}/review", summary="Análisis de la IA de un entreno", responses=_NOT_FOUND)
def get_review(activity_id: int, session: SessionDep, user: CurrentUser) -> ReviewOut | None:
    _owned_activity(session, user.id, activity_id)
    review = session.exec(select(ActivityReview).where(ActivityReview.activity_id == activity_id)).first()
    return _out(review) if review else None


@router.post(
    "/activities/{activity_id}/review",
    summary="Pedir o regenerar el análisis de un entreno",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_NOT_FOUND, 409: {"description": "Sin IA configurada"}},
)
@limiter.limit("5/minute")
def request_review(request: Request, activity_id: int, session: SessionDep, user: CurrentUser) -> ReviewOut:
    activity = _owned_activity(session, user.id, activity_id)
    if svc.active_config(session, user.id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Configura un asistente de IA en Ajustes para analizar entrenos.")
    return _out(svc.request_review(session, activity))


@router.get("/ai/reviews/latest", summary="Último análisis listo (para Hoy)")
def latest_review(session: SessionDep, user: CurrentUser) -> LatestReviewOut | None:
    review = session.exec(select(ActivityReview).where(
        ActivityReview.user_id == user.id, ActivityReview.status == "done"
    ).order_by(col(ActivityReview.id).desc())).first()  # fmt: skip
    if review is None:
        return None
    activity = session.get(Activity, review.activity_id)
    return LatestReviewOut(**_out(review).model_dump(), activity_name=activity.name or activity.sport,
                           activity_day=local_day(activity.start_time, activity.timezone).isoformat())  # fmt: skip


@router.get("/ai/review-settings", summary="Ajustes del análisis automático de entrenos")
def get_review_settings(session: SessionDep, user: CurrentUser) -> ReviewSettingsOut:
    return _settings_out(session, user.id)


@router.put("/ai/review-settings", summary="Activar o cambiar el análisis automático de entrenos")
def put_review_settings(body: ReviewSettingsIn, session: SessionDep, user: CurrentUser) -> ReviewSettingsOut:
    s = svc.get_settings(session, user.id)
    s.enabled, s.sports, s.daily_max = body.enabled, body.sports, body.daily_max
    session.add(s)
    session.commit()
    return _settings_out(session, user.id)
