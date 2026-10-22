from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlmodel import Session, delete, select

from app.api.deps import CurrentUser, SessionDep
from app.models import Activity, MatchMode, PlannedBlock, PlannedSession, User
from app.schemas.activity import ActivitySummary
from app.schemas.plan import BlockOut, MatchIn, SessionDetail, SessionIn, SessionOut
from app.services.limits import QuotaError, check_session_quota
from app.services.plan_service import blocks_of, candidate_activities, recompute, refresh_match
from app.services.plan_steps import estimated_duration_s, expand_steps

router = APIRouter(prefix="/plans", tags=["plan"])

MAX_RANGE_DAYS = 62
_NOT_FOUND = {404: {"description": "La sesión no existe o no es tuya."}}


def _owned(session: Session, user_id: int, plan_id: int) -> PlannedSession:
    planned = session.get(PlannedSession, plan_id)
    if planned is None or planned.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada.")
    return planned


def _to_out(session: Session, planned: PlannedSession) -> SessionOut:
    blocks = blocks_of(session, planned)
    steps = expand_steps(blocks)
    distances = [s.distance_m for s in steps if s.distance_m]
    return SessionOut(
        id=planned.id,
        day=planned.day,
        sport=planned.sport,
        title=planned.title,
        notes=planned.notes,
        activity_id=planned.activity_id,
        match_mode=planned.match_mode,
        compliance_score=planned.compliance_score,
        planned_duration_s=estimated_duration_s(steps),
        planned_distance_m=sum(distances) if distances else None,
        blocks=[BlockOut.model_validate(b, from_attributes=True) for b in blocks],
    )


def _to_detail(session: Session, planned: PlannedSession) -> SessionDetail:
    activity = session.get(Activity, planned.activity_id) if planned.activity_id else None
    return SessionDetail(
        **_to_out(session, planned).model_dump(),
        compliance_detail=planned.compliance_detail,
        activity=ActivitySummary.model_validate(activity, from_attributes=True) if activity else None,
    )


def _replace_blocks(session: Session, planned: PlannedSession, body: SessionIn) -> None:
    session.exec(delete(PlannedBlock).where(PlannedBlock.session_id == planned.id))
    for position, block in enumerate(body.blocks):
        session.add(PlannedBlock(session_id=planned.id, position=position, **block.model_dump()))
    session.flush()


@router.get(
    "",
    summary="Sesiones planificadas en un rango de fechas",
    description=f"Rango máximo de {MAX_RANGE_DAYS} días (pensado para la vista semanal/mensual).",
    responses={400: {"description": "Rango de fechas no válido."}},
)
def list_plans(date_from: date, date_to: date, session: SessionDep, user: CurrentUser) -> list[SessionOut]:
    if date_to < date_from or date_to - date_from > timedelta(days=MAX_RANGE_DAYS):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El rango debe ser de 0 a {MAX_RANGE_DAYS} días.")
    rows = session.exec(
        select(PlannedSession)
        .where(PlannedSession.user_id == user.id, PlannedSession.day >= date_from, PlannedSession.day <= date_to)
        .order_by(PlannedSession.day, PlannedSession.id)
    ).all()
    return [_to_out(session, p) for p in rows]


def _check_quota(session: SessionDep, user: User, day: date, exclude_id: int | None = None) -> None:
    try:
        check_session_quota(session, user, day, exclude_id)
    except QuotaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post(
    "",
    summary="Crear sesión planificada",
    description="Si ya hay una actividad ese día del mismo deporte, se empareja y se calcula el cumplimiento.",
    status_code=status.HTTP_201_CREATED,
)
def create_plan(body: SessionIn, session: SessionDep, user: CurrentUser) -> SessionDetail:
    _check_quota(session, user, body.day)
    planned = PlannedSession(user_id=user.id, **body.model_dump(exclude={"blocks"}))
    session.add(planned)
    session.flush()
    _replace_blocks(session, planned, body)
    refresh_match(session, planned)
    session.commit()
    return _to_detail(session, planned)


@router.get("/{plan_id}", summary="Detalle con plan vs real", responses=_NOT_FOUND)
def get_plan(plan_id: int, session: SessionDep, user: CurrentUser) -> SessionDetail:
    return _to_detail(session, _owned(session, user.id, plan_id))


@router.put("/{plan_id}", summary="Editar sesión planificada", responses=_NOT_FOUND)
def update_plan(plan_id: int, body: SessionIn, session: SessionDep, user: CurrentUser) -> SessionDetail:
    planned = _owned(session, user.id, plan_id)
    if body.day != planned.day:
        _check_quota(session, user, body.day, exclude_id=planned.id)
    if body.day != planned.day or body.sport != planned.sport:
        planned.match_mode = MatchMode.AUTO  # cambia el día/deporte: la actividad elegida ya no aplica
    for field, value in body.model_dump(exclude={"blocks"}).items():
        setattr(planned, field, value)
    _replace_blocks(session, planned, body)
    refresh_match(session, planned)
    session.commit()
    return _to_detail(session, planned)


@router.delete("/{plan_id}", summary="Borrar sesión planificada", status_code=204, responses=_NOT_FOUND)
def delete_plan(plan_id: int, session: SessionDep, user: CurrentUser) -> Response:
    session.delete(_owned(session, user.id, plan_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{plan_id}/candidates",
    summary="Actividades que se pueden emparejar",
    description="Actividades del mismo día local y familia de deporte.",
    responses=_NOT_FOUND,
)
def plan_candidates(plan_id: int, session: SessionDep, user: CurrentUser) -> list[ActivitySummary]:
    planned = _owned(session, user.id, plan_id)
    rows = candidate_activities(session, user.id, planned.day, planned.sport)
    return [ActivitySummary.model_validate(a, from_attributes=True) for a in rows]


@router.put(
    "/{plan_id}/match",
    summary="Cambiar la actividad emparejada",
    description="`auto`: la elige la app. `manual` + `activity_id`: fija una. `manual` sin actividad: desvincula.",
    responses={**_NOT_FOUND, 400: {"description": "La actividad no existe o no es tuya."}},
)
def set_match(plan_id: int, body: MatchIn, session: SessionDep, user: CurrentUser) -> SessionDetail:
    planned = _owned(session, user.id, plan_id)
    planned.match_mode = body.mode
    if body.mode == MatchMode.MANUAL:
        if body.activity_id is not None:
            activity = session.get(Activity, body.activity_id)
            if activity is None or activity.user_id != user.id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "La actividad no existe o no es tuya.")
        planned.activity_id = body.activity_id
        recompute(session, planned)
    else:
        refresh_match(session, planned)
    session.commit()
    return _to_detail(session, planned)
