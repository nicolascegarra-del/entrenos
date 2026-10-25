"""Envío de las sesiones del plan a Garmin Connect en segundo plano."""

import logging

from sqlmodel import Session, col, or_, select

from app.core.db import engine
from app.models import CorosOAuth, GarminCredential, GarminStatus, User, UserSettings, UserStatus
from app.services import coros_workouts, garmin_workouts, modules
from app.services.coros_oauth import CorosMcp, CorosOAuthError
from app.services.garmin_client import GarminConnectClient, GarminNotConnectedError
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _reloj_on(user_id: int) -> bool:
    with Session(engine) as session:
        return modules.enabled(session, "reloj", user_id)


@celery_app.task(name="garmin.send_workouts")
def send_workouts_task(user_id: int) -> dict:
    """Envía (o actualiza) las sesiones de los próximos 7 días a Garmin y a COROS (los que estén conectados)."""
    out: dict = {}
    if not _reloj_on(user_id):
        return out
    try:
        client = GarminConnectClient(user_id)
    except GarminNotConnectedError:
        client = None
    with Session(engine) as session:
        if client is not None:
            out["garmin"] = garmin_workouts.send_upcoming(session, user_id, client)
            client.persist()
        row = session.get(CorosOAuth, user_id)
        if row is not None and row.status == "ok":
            try:
                out["coros"] = coros_workouts.send_upcoming(session, user_id, CorosMcp(session, user_id))
            except CorosOAuthError as exc:
                logger.info("COROS: envío automático no disponible (%s)", exc)
    return out


@celery_app.task(name="garmin.delete_workout")
def delete_workout_task(user_id: int, workout_id: int) -> None:
    """Borra de Garmin el entreno de una sesión que ya no existe."""
    if not _reloj_on(user_id):
        return
    try:
        GarminConnectClient(user_id).delete_workout(workout_id)
    except Exception as exc:  # noqa: BLE001 - si no se puede (o ya no existe), no pasa nada
        logger.info("Garmin: no se pudo borrar el entreno %s (%s)", workout_id, type(exc).__name__)


@celery_app.task(name="garmin.send_workouts_all")
def send_workouts_all_task() -> int:
    """Cada 6 h: a quien tenga activado el envío automático y Garmin o COROS conectado."""
    with Session(engine) as session:
        garmin = select(GarminCredential.user_id).where(GarminCredential.status == GarminStatus.OK)
        coros = select(CorosOAuth.user_id).where(CorosOAuth.status == "ok")
        users = session.exec(
            select(UserSettings.user_id)
            .join(User, User.id == UserSettings.user_id)
            .where(
                UserSettings.garmin_workouts_auto,
                User.status == UserStatus.ACTIVE,
                or_(col(UserSettings.user_id).in_(garmin), col(UserSettings.user_id).in_(coros)),
            )
        ).all()
        users = [uid for uid in users if modules.enabled(session, "reloj", uid)]
    for uid in users:
        send_workouts_task.apply_async(args=[uid], argsrepr="(usuario)")
    return len(users)
