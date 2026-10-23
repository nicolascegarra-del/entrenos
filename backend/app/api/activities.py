from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel
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
from app.services.zones import refresh_zones

router = APIRouter(prefix="/activities", tags=["actividades"])


class RaceIn(BaseModel):
    is_race: bool


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
    q: Annotated[str | None, Query(max_length=80, description="Texto a buscar en el nombre")] = None,
) -> ActivityPage:
    query = select(Activity).where(Activity.user_id == user.id)
    if sport:
        query = query.where(Activity.sport == sport)
    if q and q.strip():
        # Búsqueda sin distinguir mayúsculas; los comodines del usuario se escapan.
        term = q.strip().replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_")
        query = query.where(col(Activity.name).ilike(f"%{term}%", escape="\\"))
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
        manual=activity.garmin_activity_id is None,
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


@router.put(
    "/{activity_id}/race",
    summary="Marcar o desmarcar como carrera a tope",
    description="Si hay carreras marcadas en el último año, solo ellas alimentan el VDOT y las previsiones.",
    responses={404: {"description": "No encontrada"}},
)
def set_race(activity_id: int, body: RaceIn, session: SessionDep, user: CurrentUser) -> dict:
    activity = _get_owned(session, user, activity_id)
    activity.is_race = body.is_race
    session.add(activity)
    session.commit()
    refresh_zones(session, user.id)  # el VDOT cambia → umbral y zonas pueden cambiar
    return {"activity_id": activity.id, "is_race": activity.is_race}


class DeleteIn(BaseModel):
    ids: list[int]


@router.delete("/{activity_id}", summary="Borrar una actividad (no vuelve con la sincronización)",
               status_code=status.HTTP_204_NO_CONTENT, responses=_NOT_FOUND)  # fmt: skip
def delete_activity(activity_id: int, session: SessionDep, user: CurrentUser) -> Response:
    from app.services.activity_delete import delete_activities

    _get_owned(session, user, activity_id)
    delete_activities(session, user.id, [activity_id])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/delete", summary="Borrar varias actividades a la vez (hasta 200)")
def delete_many(body: DeleteIn, session: SessionDep, user: CurrentUser) -> dict:
    from app.services.activity_delete import MAX_BATCH, delete_activities

    if not body.ids or len(body.ids) > MAX_BATCH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Elige entre 1 y {MAX_BATCH} actividades.")
    return {"deleted": delete_activities(session, user.id, body.ids)}


@router.get(
    "/{activity_id}/analysis",
    summary="Análisis: tiempo en zonas de FC, VO2max, parciales por km y deriva cardiaca",
    responses=_NOT_FOUND,
)
def get_analysis(activity_id: int, session: SessionDep, user: CurrentUser) -> dict:
    from app.services.activity_analysis import analysis

    return analysis(session, _get_owned(session, user, activity_id))


@router.get(
    "/{activity_id}/export",
    summary="Exportar la actividad en FIT, TCX o GPX (para llevarla a otras apps)",
    responses={**_NOT_FOUND, 422: {"description": "Formato no válido o sin datos para él (GPX sin GPS)"}},
    response_class=Response,
)
def export_activity(
    activity_id: int, session: SessionDep, user: CurrentUser, format: str = Query("fit", pattern="^(fit|tcx|gpx)$")
) -> Response:
    from app.services.activity_export import ExportError, export

    activity = _get_owned(session, user, activity_id)
    try:
        data, media, name = export(session, activity, format)
    except ExportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
