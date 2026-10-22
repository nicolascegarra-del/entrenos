"""Recorridos repetidos y comparador de dos actividades."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.models import Activity
from app.services import routes as svc

router = APIRouter(prefix="/routes", tags=["recorridos"])
_NOT_FOUND = {404: {"description": "No encontrado"}}


def _owned(session: SessionDep, user_id: int, activity_id: int) -> Activity:
    activity = session.get(Activity, activity_id)
    if activity is None or activity.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Actividad no encontrada.")
    return activity


@router.get("", summary="Recorridos que has repetido (al menos dos veces)")
def list_routes(session: SessionDep, user: CurrentUser) -> list[dict]:
    return [svc.group_out(g) for g in svc.group_routes(session, user.id)]


@router.get("/compare", summary="Comparar dos actividades alineadas por distancia", responses=_NOT_FOUND)
def compare(
    session: SessionDep,
    user: CurrentUser,
    a: Annotated[int, Query(description="Actividad de referencia")],
    b: Annotated[int, Query(description="Actividad a comparar con la de referencia")],
) -> dict:
    if a == b:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Elige dos actividades distintas.")
    return svc.compare(session, _owned(session, user.id, a), _owned(session, user.id, b))


@router.get("/by-activity/{activity_id}", summary="Recorrido al que pertenece una actividad", responses=_NOT_FOUND)
def route_of_activity(activity_id: int, session: SessionDep, user: CurrentUser) -> dict | None:
    _owned(session, user.id, activity_id)
    return svc.route_for_activity(session, user.id, activity_id)


@router.get("/{route_id}", summary="Detalle de un recorrido con todos sus intentos", responses=_NOT_FOUND)
def get_route(route_id: int, session: SessionDep, user: CurrentUser) -> dict:
    group = next((g for g in svc.group_routes(session, user.id) if g.rep.id == route_id), None)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recorrido no encontrado.")
    return svc.group_out(group, session)
