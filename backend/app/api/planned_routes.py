"""Rutas planificadas: calcular en el mapa (openrouteservice), guardar, exportar a GPX y usar en el plan."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep, require_module
from app.core.rate_limit import limiter
from app.models import PlannedRoute, PlannedSession
from app.services import route_planner as rp

_RUTAS = [Depends(require_module("rutas"))]
router = APIRouter(prefix="/planned-routes", tags=["rutas"], dependencies=_RUTAS)

_NOT_FOUND = {404: {"description": "La ruta no existe o no es tuya."}}
Mode = str


class PointIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class PlanIn(BaseModel):
    mode: Mode = Field(pattern="^(asfalto|trail|bici|mtb)$")
    points: list[PointIn] = Field(min_length=2, max_length=rp.MAX_POINTS)


class PlanOut(BaseModel):
    mode: str
    geometry: list[list[float | None]]
    distance_m: int
    ascent_m: int
    descent_m: int
    profile: list[list[float]]
    surfaces: list[dict]
    waytypes: list[dict]
    max_altitude_m: int | None
    min_altitude_m: int | None
    estimated_s: int
    estimate_basis: str


class RouteIn(PlanIn):
    name: str = Field(min_length=1, max_length=120)


class RouteBrief(BaseModel):
    id: int
    name: str
    mode: str
    distance_m: int
    ascent_m: int
    descent_m: int
    estimated_s: int | None
    # Traza reducida (unos 60 puntos [lat, lon]) para la miniatura de la lista.
    preview: list[list[float]]
    created_at: datetime


class RouteOut(RouteBrief):
    waypoints: list[list[float]]
    geometry: list[list[float | None]]
    profile: list[list[float]]
    surfaces: list[dict]
    waytypes: list[dict]
    sessions: list[dict]  # sesiones del plan que usan esta ruta


class RoutePage(BaseModel):
    items: list[RouteBrief]
    total: int


class SessionRouteIn(BaseModel):
    planned_route_id: int | None = None


def _error(exc: rp.RouteError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


def _owned(session: SessionDep, user_id: int, route_id: int) -> PlannedRoute:
    route = session.get(PlannedRoute, route_id)
    if route is None or route.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ruta no encontrada.")
    return route


def _brief(route: PlannedRoute) -> RouteBrief:
    preview = [[p[0], p[1]] for p in rp._simplify(route.geometry, 60)]
    return RouteBrief(**route.model_dump(include=set(RouteBrief.model_fields) - {"preview"}), preview=preview)


def _detail(session: SessionDep, route: PlannedRoute) -> RouteOut:
    rows = session.exec(
        select(PlannedSession)
        .where(PlannedSession.planned_route_id == route.id, PlannedSession.user_id == route.user_id)
        .order_by(PlannedSession.day)
    ).all()
    return RouteOut(
        **_brief(route).model_dump(),
        waypoints=route.waypoints,
        geometry=route.geometry,
        profile=route.profile,
        surfaces=route.surfaces,
        waytypes=route.waytypes,
        sessions=[{"id": s.id, "day": s.day.isoformat(), "title": s.title} for s in rows],
    )


def _compute(session: SessionDep, user_id: int, body: PlanIn) -> dict:
    try:
        return rp.plan(session, user_id, [rp.Waypoint(p.lat, p.lon) for p in body.points], body.mode)
    except rp.RouteError as exc:
        raise _error(exc) from exc


def _apply(route: PlannedRoute, body: RouteIn, result: dict) -> None:
    route.name = body.name.strip()
    route.mode = body.mode
    route.waypoints = [[p.lat, p.lon] for p in body.points]
    for key in ("geometry", "profile", "surfaces", "waytypes", "distance_m", "ascent_m", "descent_m", "estimated_s"):
        setattr(route, key, result[key])


@router.post(
    "/plan",
    summary="Calcular una ruta sin guardarla",
    description="Por carreteras o senderos según el modo, con altitud, desnivel, superficies y tiempo estimado.",
    responses={422: {"description": "Sin camino entre los puntos, sin clave del servicio o cupo agotado"}},
)
@limiter.limit("60/minute")
def plan_route(request: Request, body: PlanIn, session: SessionDep, user: CurrentUser) -> PlanOut:
    return PlanOut(**_compute(session, user.id, body))


@router.get("/geocode", summary="Buscar un lugar para centrar el mapa")
@limiter.limit("60/minute")
def geocode(request: Request, user: CurrentUser, q: str = Query(min_length=2, max_length=100)) -> list[dict]:
    try:
        return rp.geocode(q)
    except rp.RouteError as exc:
        raise _error(exc) from exc


@router.get("", summary="Tus rutas, de la más reciente a la más antigua")
def list_routes(
    session: SessionDep, user: CurrentUser, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)
) -> RoutePage:
    where = PlannedRoute.user_id == user.id
    rows = session.exec(
        select(PlannedRoute).where(where).order_by(col(PlannedRoute.created_at).desc()).offset(offset).limit(limit)
    ).all()
    total = session.exec(select(func.count()).select_from(PlannedRoute).where(where)).one()
    return RoutePage(items=[_brief(r) for r in rows], total=total)


@router.post("", summary="Guardar una ruta (se calcula en el servidor)", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_route(request: Request, body: RouteIn, session: SessionDep, user: CurrentUser) -> RouteOut:
    route = PlannedRoute(user_id=user.id, name="", mode=body.mode, distance_m=0, ascent_m=0, descent_m=0)
    _apply(route, body, _compute(session, user.id, body))
    session.add(route)
    session.commit()
    session.refresh(route)
    return _detail(session, route)


@router.get("/{route_id}", summary="Detalle de una ruta", responses=_NOT_FOUND)
def get_route(route_id: int, session: SessionDep, user: CurrentUser) -> RouteOut:
    return _detail(session, _owned(session, user.id, route_id))


@router.put("/{route_id}", summary="Editar una ruta (nombre, modo o puntos)", responses=_NOT_FOUND)
@limiter.limit("30/minute")
def update_route(request: Request, route_id: int, body: RouteIn, session: SessionDep, user: CurrentUser) -> RouteOut:
    route = _owned(session, user.id, route_id)
    _apply(route, body, _compute(session, user.id, body))
    route.updated_at = datetime.now(UTC)
    session.add(route)
    session.commit()
    session.refresh(route)
    return _detail(session, route)


@router.delete("/{route_id}", summary="Borrar una ruta", status_code=204, responses=_NOT_FOUND)
def delete_route(route_id: int, session: SessionDep, user: CurrentUser) -> Response:
    route = _owned(session, user.id, route_id)
    for planned in session.exec(select(PlannedSession).where(PlannedSession.planned_route_id == route.id)).all():
        planned.planned_route_id = None
        session.add(planned)
    session.delete(route)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{route_id}/gpx",
    summary="Descargar la ruta en GPX (para importarla en el reloj)",
    responses={**_NOT_FOUND, 200: {"content": {"application/gpx+xml": {}}}},
)
def route_gpx(route_id: int, session: SessionDep, user: CurrentUser) -> Response:
    route = _owned(session, user.id, route_id)
    safe = "".join(c if c.isalnum() else "-" for c in route.name.lower()).strip("-")[:40] or "ruta"
    return Response(
        rp.to_gpx(route.name, route.geometry),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{safe}.gpx"'},
    )


session_router = APIRouter(prefix="/plans", tags=["plan"], dependencies=_RUTAS)


@session_router.put(
    "/{plan_id}/route",
    summary="Asociar (o quitar) una ruta a una sesión del plan",
    responses={404: {"description": "La sesión o la ruta no existen o no son tuyas."}},
)
def set_session_route(plan_id: int, body: SessionRouteIn, session: SessionDep, user: CurrentUser) -> dict:
    planned = session.get(PlannedSession, plan_id)
    if planned is None or planned.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada.")
    route = _owned(session, user.id, body.planned_route_id) if body.planned_route_id else None
    planned.planned_route_id = route.id if route else None
    session.add(planned)
    session.commit()
    return {"planned_route_id": planned.planned_route_id, "route": rp.summary(route) if route else None}
