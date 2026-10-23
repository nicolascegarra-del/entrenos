"""Envío de las sesiones del plan a Garmin Connect en segundo plano."""

import logging

from sqlmodel import Session, select

from app.core.db import engine
from app.models import GarminCredential, GarminStatus, User, UserSettings, UserStatus
from app.services import garmin_workouts
from app.services.garmin_client import GarminConnectClient, GarminNotConnectedError
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="garmin.send_workouts")
def send_workouts_task(user_id: int) -> dict:
    """Envía (o actualiza) las sesiones de los próximos 7 días."""
    try:
        client = GarminConnectClient(user_id)
    except GarminNotConnectedError:
        return {}
    with Session(engine) as session:
        counts = garmin_workouts.send_upcoming(session, user_id, client)
    client.persist()
    return counts


@celery_app.task(name="garmin.delete_workout")
def delete_workout_task(user_id: int, workout_id: int) -> None:
    """Borra de Garmin el entreno de una sesión que ya no existe."""
    try:
        GarminConnectClient(user_id).delete_workout(workout_id)
    except Exception as exc:  # noqa: BLE001 - si no se puede (o ya no existe), no pasa nada
        logger.info("Garmin: no se pudo borrar el entreno %s (%s)", workout_id, type(exc).__name__)


@celery_app.task(name="garmin.send_workouts_all")
def send_workouts_all_task() -> int:
    """Cada 6 h: a quien tenga activado el envío automático y Garmin conectado."""
    with Session(engine) as session:
        users = session.exec(
            select(UserSettings.user_id)
            .join(GarminCredential, GarminCredential.user_id == UserSettings.user_id)
            .join(User, User.id == UserSettings.user_id)
            .where(
                UserSettings.garmin_workouts_auto,
                GarminCredential.status == GarminStatus.OK,
                User.status == UserStatus.ACTIVE,
            )
        ).all()
    for uid in users:
        send_workouts_task.apply_async(args=[uid], argsrepr="(usuario)")
    return len(users)
