"""Entrenador IA: tu ficha («Lo que sé de ti»), consentimiento, revisión semanal y propuestas de cambio del plan."""

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep, require_module
from app.models import CoachMemory, PlannedSession, PlanProposal, WeeklyCheckin
from app.services import coach, weekly_review

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coach", tags=["entrenador IA"], dependencies=[Depends(require_module("ia"))])


class CoachSettingsOut(BaseModel):
    health_consent: bool
    health_consent_at: datetime | None
    interview_done: bool
    weekly_review: bool
    categories: dict[str, str] = coach.CATEGORIES
    health_categories: list[str] = list(coach.HEALTH)


class CoachSettingsIn(BaseModel):
    health_consent: bool | None = None
    weekly_review: bool | None = None


class MemoryIn(BaseModel):
    category: str = Field(min_length=1, max_length=16)
    content: str = Field(min_length=1, max_length=500)


class MemoryOut(BaseModel):
    id: int
    category: str
    content: str
    source: str
    created_at: datetime
    updated_at: datetime | None


class CheckinIn(BaseModel):
    energia: int | None = Field(default=None, ge=1, le=5)
    sueno: int | None = Field(default=None, ge=1, le=5)
    estres: int | None = Field(default=None, ge=1, le=5)
    motivacion: int | None = Field(default=None, ge=1, le=5)
    molestias: str | None = Field(default=None, max_length=500)
    comentario: str | None = Field(default=None, max_length=500)


class CheckinOut(BaseModel):
    id: int
    week_start: date
    status: str
    answers: dict
    summary: str
    error: str
    effects: list | None
    updated_at: datetime | None


class ProposalOut(BaseModel):
    id: int
    planned_session_id: int
    session_title: str | None
    session_day: date | None
    summary: str
    reason: str
    change: dict
    status: str
    created_at: datetime


def _settings_out(session: SessionDep, user_id: int) -> CoachSettingsOut:
    s = coach.settings(session, user_id)
    return CoachSettingsOut(health_consent=s.health_consent, health_consent_at=s.health_consent_at,
                            interview_done=bool(s.interview_done_at), weekly_review=s.weekly_review)  # fmt: skip


def _proposal_out(session: SessionDep, p: PlanProposal) -> ProposalOut:
    planned = session.get(PlannedSession, p.planned_session_id)
    return ProposalOut(id=p.id, planned_session_id=p.planned_session_id,
                       session_title=planned.title if planned else None,
                       session_day=planned.day if planned else None, summary=coach.describe(p, planned),
                       reason=p.reason, change=p.change, status=p.status, created_at=p.created_at)  # fmt: skip


@router.get("/settings", summary="Consentimiento de salud, entrevista y revisión semanal")
def get_settings_(session: SessionDep, user: CurrentUser) -> CoachSettingsOut:
    return _settings_out(session, user.id)


@router.put("/settings", summary="Cambiar consentimiento de salud o revisión semanal")
def put_settings(body: CoachSettingsIn, session: SessionDep, user: CurrentUser) -> CoachSettingsOut:
    if body.health_consent is not None:
        coach.set_consent(session, user.id, body.health_consent)
    if body.weekly_review is not None:
        s = coach.settings(session, user.id)
        s.weekly_review = body.weekly_review
        session.add(s)
        session.commit()
    return _settings_out(session, user.id)


@router.get("/memories", summary="Lo que el entrenador sabe de ti")
def list_memories(session: SessionDep, user: CurrentUser) -> list[MemoryOut]:
    return [MemoryOut.model_validate(m, from_attributes=True) for m in coach.memories(session, user.id)]


@router.post("/memories", summary="Añadir un dato a tu ficha", status_code=status.HTTP_201_CREATED)
def add_memory(body: MemoryIn, session: SessionDep, user: CurrentUser) -> MemoryOut:
    try:
        m = coach.save_memory(session, user.id, body.category, body.content, source="usuario")
    except coach.CoachError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return MemoryOut.model_validate(m, from_attributes=True)


@router.put("/memories/{memory_id}", summary="Corregir un dato de tu ficha")
def edit_memory(memory_id: int, body: MemoryIn, session: SessionDep, user: CurrentUser) -> MemoryOut:
    try:
        m = coach.save_memory(session, user.id, body.category, body.content, source="usuario", replaces=memory_id)
    except coach.CoachError as exc:
        code = status.HTTP_404_NOT_FOUND if "No existe" in str(exc) else status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(code, str(exc)) from exc
    return MemoryOut.model_validate(m, from_attributes=True)


@router.delete("/memories/{memory_id}", summary="Borrar un dato de tu ficha", status_code=204)
def delete_memory(memory_id: int, session: SessionDep, user: CurrentUser) -> Response:
    row = session.get(CoachMemory, memory_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dato no encontrado.")
    coach.forget(session, user.id, memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/checkin", summary="Revisión semanal más reciente (o ninguna)")
def get_checkin(session: SessionDep, user: CurrentUser) -> CheckinOut | None:
    row = weekly_review.current(session, user.id)
    return CheckinOut.model_validate(row, from_attributes=True) if row else None


@router.post("/checkin", summary="Abrir la revisión de esta semana (si no existe)")
def open_checkin(session: SessionDep, user: CurrentUser) -> CheckinOut:
    return CheckinOut.model_validate(weekly_review.open_week(session, user.id), from_attributes=True)


@router.post(
    "/checkin/{checkin_id}/answers",
    summary="Responder la revisión semanal (el resumen se escribe en segundo plano)",
    responses={404: {"description": "No existe"}, 409: {"description": "Sin asistente de IA"}},
)
def answer_checkin(checkin_id: int, body: CheckinIn, session: SessionDep, user: CurrentUser) -> CheckinOut:
    from app.services.activity_review import active_config

    row = session.get(WeeklyCheckin, checkin_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revisión no encontrada.")
    if active_config(session, user.id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Configura un asistente de IA en Ajustes → Asistente IA.")
    try:
        row.answers = weekly_review.clean_answers(body.model_dump())
    except coach.CoachError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    row.status, row.error, row.summary, row.effects = "processing", "", "", None
    session.add(row)
    session.commit()
    from app.tasks.coach import weekly_summary_task

    try:
        weekly_summary_task.apply_async(args=[row.id])
    except Exception:  # noqa: BLE001 - sin cola, el resumen se escribe aquí mismo
        logger.warning("Revisión semanal: sin cola, se genera en la petición")
        weekly_review.generate(session, row.id)
    session.refresh(row)
    return CheckinOut.model_validate(row, from_attributes=True)


@router.get("/proposals", summary="Propuestas de cambio del plan (pendientes por defecto)")
def list_proposals(
    session: SessionDep, user: CurrentUser, status_: str = Query("pending", alias="status")
) -> list[ProposalOut]:
    rows = session.exec(
        select(PlanProposal)
        .where(PlanProposal.user_id == user.id, PlanProposal.status == status_)
        .order_by(PlanProposal.created_at.desc())  # type: ignore[attr-defined]
        .limit(30)
    ).all()
    return [_proposal_out(session, p) for p in rows]


@router.post("/proposals/{proposal_id}/{decision}", summary="Aceptar o rechazar una propuesta del entrenador")
def decide_proposal(proposal_id: int, decision: str, session: SessionDep, user: CurrentUser) -> ProposalOut:
    if decision not in ("accept", "reject"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Acción desconocida.")
    try:
        p = coach.decide(session, user.id, proposal_id, decision == "accept")
    except coach.CoachError as exc:
        code = status.HTTP_404_NOT_FOUND if "no encontrada" in str(exc) else status.HTTP_409_CONFLICT
        raise HTTPException(code, str(exc)) from exc
    return _proposal_out(session, p)
