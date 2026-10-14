from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import col, distinct, or_, select

from app.api.deps import CurrentUser, SessionDep
from app.models import Activity, ActivityStream, Device, Lap
from app.schemas.activity import (
    ActivityDetail,
    ActivityPage,
    ActivitySummary,
    DeviceRead,
    LapRead,
    StreamsResponse,
)
from app.services.streams import downsample

router = APIRouter(prefix="/activities", tags=["actividades"])

_NOT_FOUND = {404: {"description": "La actividad no existe o no es tuya."}}


def _encode_cursor(activity: Activity) -> str:
    return f"{int(activity.start_time.timestamp() * 1_000_000)}_{activity.id}"


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        micros, activity_id = cursor.split("_")
        return datetime.fromtimestamp(int(micros) / 1_000_000, tz=UTC), int(activity_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cursor no válido.") from exc


def _get_owned(session: SessionDep, user: CurrentUser, activity_id: int) -> Activity:
    activity = session.get(Activity, activity_id)
    if activity is None or activity.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Actividad no encontrada.")
    return activity


@router.get(
    "",
    summary="Listar actividades",
    description="Paginación por cursor (más recientes primero). Filtros opcionales por deporte y fechas.",
    responses={400: {"description": "Cursor no válido."}},
)
def list_activities(
    session: SessionDep,
    user: CurrentUser,
    sport: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ActivityPage:
    query = select(Activity).where(Activity.user_id == user.id)
    if sport:
        query = query.where(Activity.sport == sport)
    if date_from:
        query = query.where(Activity.start_time >= date_from)
    if date_to:
        query = query.where(Activity.start_time < date_to)
    if cursor:
        cursor_time, cursor_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                Activity.start_time < cursor_time,
                (Activity.start_time == cursor_time) & (col(Activity.id) < cursor_id),
            )
        )
    rows = session.exec(query.order_by(col(Activity.start_time).desc(), col(Activity.id).desc()).limit(limit + 1)).all()
    items = rows[:limit]
    return ActivityPage(
        items=[ActivitySummary.model_validate(a, from_attributes=True) for a in items],
        next_cursor=_encode_cursor(items[-1]) if len(rows) > limit else None,
    )


@router.get("/sports", summary="Deportes con actividades")
def list_sports(session: SessionDep, user: CurrentUser) -> list[str]:
    rows = session.exec(select(distinct(Activity.sport)).where(Activity.user_id == user.id))
    return sorted(rows.all())


@router.get("/{activity_id}", summary="Detalle de actividad", responses=_NOT_FOUND)
def get_activity(activity_id: int, session: SessionDep, user: CurrentUser) -> ActivityDetail:
    activity = _get_owned(session, user, activity_id)
    laps = session.exec(select(Lap).where(Lap.activity_id == activity.id).order_by(Lap.index)).all()
    channels = session.exec(select(ActivityStream.channel).where(ActivityStream.activity_id == activity.id)).all()
    device = session.get(Device, activity.device_id) if activity.device_id else None
    return ActivityDetail(
        **ActivitySummary.model_validate(activity, from_attributes=True).model_dump(),
        moving_duration_s=activity.moving_duration_s,
        max_hr=activity.max_hr,
        calories=activity.calories,
        device=DeviceRead(id=device.id, name=device.name) if device else None,
        laps=[LapRead.model_validate(lap, from_attributes=True) for lap in laps],
        channels=sorted(channels),
    )


@router.get(
    "/{activity_id}/streams",
    summary="Series temporales de una actividad",
    description="Devuelve los canales pedidos (todos si se omite), reducidos a `max_points` puntos.",
    responses=_NOT_FOUND,
)
def get_streams(
    activity_id: int,
    session: SessionDep,
    user: CurrentUser,
    channels: Annotated[str | None, Query(description="Lista separada por comas, ej. time,hr,speed")] = None,
    max_points: Annotated[int, Query(ge=50, le=5000)] = 1000,
) -> StreamsResponse:
    activity = _get_owned(session, user, activity_id)
    query = select(ActivityStream).where(ActivityStream.activity_id == activity.id)
    if channels:
        query = query.where(col(ActivityStream.channel).in_([c.strip() for c in channels.split(",")]))
    data = downsample({s.channel: s.values for s in session.exec(query).all()}, max_points)
    return StreamsResponse(points=max((len(v) for v in data.values()), default=0), channels=data)
