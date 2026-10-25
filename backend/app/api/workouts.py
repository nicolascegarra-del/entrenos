"""Enviar sesiones del plan al reloj: Garmin Connect (manual o automático) y descarga en .FIT."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep, require_module
from app.core.rate_limit import limiter
from app.models import CorosOAuth, GarminCredential, GarminStatus, PlannedSession, UserSettings
from app.services import coros_workouts, garmin_workouts, modules
from app.services.coros_oauth import CorosMcp, CorosOAuthError
from app.services.garmin_client import GarminConnectClient, GarminNotConnectedError
from app.services.plan_service import blocks_of
from app.services.workout_export import WorkoutExportError, fit_filename, fit_workout

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plan"])
# Solo el envío al reloj depende del módulo; descargar el .FIT sigue disponible.
_RELOJ = [Depends(require_module("reloj"))]

_NOT_FOUND = {404: {"description": "La sesión no existe o no es tuya."}}


class WorkoutSettings(BaseModel):
    auto: bool


class WorkoutSettingsOut(WorkoutSettings):
    garmin_connected: bool
    coros_connected: bool = False
    days: int = garmin_workouts.UPCOMING_DAYS


class GarminState(BaseModel):
    garmin_status: str
    garmin_error: str
    garmin_sent_at: datetime | None


class CorosState(BaseModel):
    coros_status: str
    coros_error: str
    coros_sent_at: datetime | None


def _owned(session: SessionDep, user_id: int, plan_id: int) -> PlannedSession:
    planned = session.get(PlannedSession, plan_id)
    if planned is None or planned.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada.")
    return planned


def _client(user_id: int) -> GarminConnectClient:
    try:
        return GarminConnectClient(user_id)
    except GarminNotConnectedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Conecta Garmin en Ajustes → Conexiones para enviar sesiones."
        ) from exc


def _connected(session: SessionDep, user_id: int) -> bool:
    cred = session.get(GarminCredential, user_id)
    return cred is not None and cred.status == GarminStatus.OK


def _coros_connected(session: SessionDep, user_id: int) -> bool:
    row = session.get(CorosOAuth, user_id)
    return row is not None and row.status == "ok"


def queue_send(session, user_id: int) -> None:
    """Si el envío automático está activado, manda en segundo plano las sesiones de los próximos 7 días."""
    settings = session.get(UserSettings, user_id)
    if not (settings and settings.garmin_workouts_auto):
        return
    if not modules.enabled(session, "reloj"):
        return
    if not (_connected(session, user_id) or _coros_connected(session, user_id)):
        return
    from app.tasks.workouts import send_workouts_task

    try:
        send_workouts_task.apply_async(args=[user_id], argsrepr="(usuario)")
    except Exception:  # noqa: BLE001 - sin cola, se enviará en la siguiente pasada automática
        logger.warning("No se pudo encolar el envío de entrenos a Garmin")


def queue_delete(user_id: int, workout_id: int | None) -> None:
    """Borra en segundo plano el entreno de Garmin de una sesión que se ha borrado."""
    if not workout_id:
        return
    from app.tasks.workouts import delete_workout_task

    try:
        delete_workout_task.apply_async(args=[user_id, workout_id], argsrepr="(usuario, entreno)")
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo encolar el borrado de un entreno en Garmin")


@router.get("/workouts/settings", dependencies=_RELOJ, summary="Envío de sesiones a Garmin: automático o no")
def get_workout_settings(session: SessionDep, user: CurrentUser) -> WorkoutSettingsOut:
    settings = session.get(UserSettings, user.id)
    return WorkoutSettingsOut(
        auto=bool(settings and settings.garmin_workouts_auto),
        garmin_connected=_connected(session, user.id),
        coros_connected=_coros_connected(session, user.id),
    )


@router.put("/workouts/settings", dependencies=_RELOJ, summary="Activar o desactivar el envío automático a Garmin")
def put_workout_settings(body: WorkoutSettings, session: SessionDep, user: CurrentUser) -> WorkoutSettingsOut:
    settings = session.get(UserSettings, user.id) or UserSettings(user_id=user.id)
    settings.garmin_workouts_auto = body.auto
    session.add(settings)
    session.commit()
    if body.auto:
        queue_send(session, user.id)
    return get_workout_settings(session, user)


@router.post(
    "/plans/{plan_id}/garmin",
    dependencies=_RELOJ,
    summary="Enviar la sesión a Garmin Connect (se programa en su día y llega al reloj al sincronizar)",
    responses={**_NOT_FOUND, 409: {"description": "Garmin no conectado"}},
)
@limiter.limit("20/minute")
def send_to_garmin(request: Request, plan_id: int, session: SessionDep, user: CurrentUser) -> GarminState:
    planned = _owned(session, user.id, plan_id)
    client = _client(user.id)
    garmin_workouts.send(session, planned, client)
    client.persist()
    return GarminState.model_validate(planned, from_attributes=True)


@router.delete(
    "/plans/{plan_id}/garmin", dependencies=_RELOJ, summary="Quitar la sesión de Garmin Connect", responses=_NOT_FOUND
)
def remove_from_garmin(plan_id: int, session: SessionDep, user: CurrentUser) -> GarminState:
    planned = _owned(session, user.id, plan_id)
    if planned.garmin_workout_id:
        garmin_workouts.remove(session, planned, _client(user.id))
    return GarminState.model_validate(planned, from_attributes=True)


@router.post(
    "/workouts/send-upcoming",
    dependencies=_RELOJ,
    summary="Enviar a Garmin las sesiones de hoy y los próximos 6 días",
    responses={409: {"description": "Garmin no conectado"}},
)
@limiter.limit("6/minute")
def send_upcoming(request: Request, session: SessionDep, user: CurrentUser) -> dict:
    """Envía a todos los relojes conectados (Garmin y COROS) y suma los resultados."""
    garmin, coros = _connected(session, user.id), _coros_connected(session, user.id)
    if not garmin and not coros:
        raise HTTPException(status.HTTP_409_CONFLICT, "Conecta Garmin o COROS en Ajustes → Conexiones.")
    total = {"sent": 0, "unchanged": 0, "error": 0}
    if garmin:
        client = _client(user.id)
        for k, v in garmin_workouts.send_upcoming(session, user.id, client).items():
            total[k] += v
        client.persist()
    if coros:
        for k, v in coros_workouts.send_upcoming(session, user.id, CorosMcp(session, user.id)).items():
            total[k] += v
    return total


@router.post(
    "/plans/{plan_id}/coros",
    dependencies=_RELOJ,
    summary="Enviar la sesión al calendario de COROS (conexión oficial)",
    responses={**_NOT_FOUND, 409: {"description": "COROS no conectado"}},
)
@limiter.limit("20/minute")
def send_to_coros(request: Request, plan_id: int, session: SessionDep, user: CurrentUser) -> CorosState:
    planned = _owned(session, user.id, plan_id)
    try:
        mcp = CorosMcp(session, user.id)
    except CorosOAuthError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    coros_workouts.send(session, planned, mcp)
    return CorosState.model_validate(planned, from_attributes=True)


@router.get(
    "/plans/{plan_id}/workout.fit",
    summary="Descargar la sesión como entreno .FIT (Garmin por USB, Wahoo, Hammerhead…)",
    responses={**_NOT_FOUND, 422: {"description": "Deporte sin soporte o sesión sin bloques"}},
    response_class=Response,
)
def download_fit(plan_id: int, session: SessionDep, user: CurrentUser) -> Response:
    planned = _owned(session, user.id, plan_id)
    try:
        data = fit_workout(planned, blocks_of(session, planned))
    except WorkoutExportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return Response(
        content=data,
        media_type="application/vnd.ant.fit",
        headers={"Content-Disposition": f'attachment; filename="{fit_filename(planned)}"'},
    )
