"""
Enviar las sesiones del plan a Garmin Connect (y de ahí al reloj).

- `send`: sube la sesión como entreno y la programa en su día. Si ya estaba enviada y no ha cambiado
  (misma huella de bloques y día), no hace nada; si ha cambiado, borra la anterior y sube la nueva.
- `remove`: la quita de Garmin (al borrar la sesión o a petición).
- `send_upcoming`: las sesiones de hoy y los próximos 6 días (manual con un botón, o automático cada
  6 h y al cambiar el plan si está activado en Ajustes).

El reloj recibe los entrenos programados al sincronizar con Garmin Connect. No se tocan entrenos
que no haya creado la app (solo se borran los ids guardados en cada sesión).
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from sqlmodel import Session, col, select

from app.models import PlannedSession
from app.services.plan_service import blocks_of
from app.services.workout_export import WorkoutExportError, content_hash, garmin_workout

logger = logging.getLogger(__name__)

UPCOMING_DAYS = 7


class WorkoutTarget(Protocol):
    """Lo que necesita el envío (el cliente real de Garmin o uno falso en los tests)."""

    def upload_workout(self, workout: dict) -> dict: ...
    def schedule_workout(self, workout_id: int, day: str) -> dict: ...
    def delete_workout(self, workout_id: int) -> None: ...


def _id(data: dict, *keys: str) -> int | None:
    for k in keys:
        if isinstance(data.get(k), int):
            return data[k]
    return None


def _delete_remote(client: WorkoutTarget, workout_id: int | None) -> None:
    if not workout_id:
        return
    try:
        client.delete_workout(workout_id)
    except Exception as exc:  # noqa: BLE001 - si ya no existe en Garmin, no pasa nada
        logger.info("Garmin: no se pudo borrar el entreno %s (%s)", workout_id, type(exc).__name__)


def send(session: Session, planned: PlannedSession, client: WorkoutTarget) -> str:
    """
    Envía (o reenvía si cambió) la sesión a Garmin.

    Returns:
        "sent" (subida), "unchanged" (ya estaba igual) o "error" (se guarda el motivo en la sesión).
    """
    try:
        workout = garmin_workout(planned, blocks_of(session, planned))
    except WorkoutExportError as exc:
        planned.garmin_status, planned.garmin_error = "error", str(exc)[:255]
        session.add(planned)
        session.commit()
        return "error"
    digest = content_hash(planned, workout)
    if planned.garmin_status == "sent" and planned.garmin_hash == digest and planned.garmin_workout_id:
        return "unchanged"
    try:
        _delete_remote(client, planned.garmin_workout_id)
        created = client.upload_workout(workout)
        workout_id = _id(created, "workoutId", "id")
        if workout_id is None:
            raise RuntimeError("Garmin no devolvió el id del entreno.")
        scheduled = client.schedule_workout(workout_id, planned.day.isoformat())
    except Exception as exc:
        from garminconnect import GarminConnectAuthenticationError

        logger.warning("Garmin: fallo al enviar la sesión %s (%s)", planned.id, type(exc).__name__)
        planned.garmin_status = "error"
        planned.garmin_error = (
            "La sesión de Garmin ha caducado: vuelve a conectar Garmin en Ajustes."
            if isinstance(exc, GarminConnectAuthenticationError)
            else "Garmin no aceptó el entreno. Inténtalo más tarde."
        )
        session.add(planned)
        session.commit()
        return "error"
    planned.garmin_workout_id = workout_id
    planned.garmin_schedule_id = _id(scheduled, "workoutScheduleId", "scheduleId", "id")
    planned.garmin_status, planned.garmin_error, planned.garmin_hash = "sent", "", digest
    planned.garmin_sent_at = datetime.now(UTC)
    session.add(planned)
    session.commit()
    return "sent"


def remove(session: Session, planned: PlannedSession, client: WorkoutTarget) -> None:
    """Quita la sesión de Garmin y limpia su estado."""
    _delete_remote(client, planned.garmin_workout_id)
    planned.garmin_workout_id = planned.garmin_schedule_id = None
    planned.garmin_status = planned.garmin_error = planned.garmin_hash = ""
    planned.garmin_sent_at = None
    session.add(planned)
    session.commit()


def upcoming(session: Session, user_id: int, today: date | None = None) -> list[PlannedSession]:
    """Sesiones de hoy a 6 días vista que se pueden enviar (carrera y bici sin actividad hecha)."""
    from app.services.plan_steps import sport_family

    today = today or date.today()
    rows = session.exec(
        select(PlannedSession)
        .where(
            PlannedSession.user_id == user_id,
            col(PlannedSession.day) >= today,
            col(PlannedSession.day) < today + timedelta(days=UPCOMING_DAYS),
            col(PlannedSession.activity_id).is_(None),
        )
        .order_by(col(PlannedSession.day), col(PlannedSession.id))
    ).all()
    return [p for p in rows if sport_family(p.sport) in ("running", "cycling")]


def send_upcoming(session: Session, user_id: int, client: WorkoutTarget, today: date | None = None) -> dict[str, int]:
    """Envía las sesiones de los próximos 7 días. Returns: cuántas se enviaron, seguían igual o fallaron."""
    counts = {"sent": 0, "unchanged": 0, "error": 0}
    for planned in upcoming(session, user_id, today):
        counts[send(session, planned, client)] += 1
    return counts
