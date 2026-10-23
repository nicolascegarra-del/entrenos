"""
Borrar actividades (una o varias) sin que vuelvan con la siguiente sincronización.

Al borrar se guarda una marca (`DeletedActivity`) con su id en la fuente y su hora de inicio. La
sincronización de Garmin y la importación común (`save_imported`: COROS, Health Connect, Apple, ficheros)
la consultan y no la vuelven a crear. Las vueltas, series, análisis y sensaciones caen en cascada; las
sesiones del plan emparejadas se vuelven a emparejar y los tests o récords se quedan sin la actividad.
"""

import logging
from datetime import datetime, timedelta

from sqlmodel import Session, col, select

from app.models import Activity, ActivityRaw, DeletedActivity, PlannedSession

logger = logging.getLogger(__name__)

MAX_BATCH = 200
WINDOW_S = 120  # misma ventana que el deduplicado entre fuentes


def is_deleted(
    session: Session, user_id: int, start_time: datetime, source: str | None = None, external_key: str | None = None
) -> bool:
    """¿La persona borró este entreno? (mismo id en la fuente o misma hora de inicio ±2 min)."""
    if source and external_key:
        same = session.exec(select(DeletedActivity.id).where(
            DeletedActivity.user_id == user_id, DeletedActivity.source == source,
            DeletedActivity.external_key == str(external_key),
        )).first()  # fmt: skip
        if same is not None:
            return True
    window = timedelta(seconds=WINDOW_S)
    return session.exec(select(DeletedActivity.id).where(
        DeletedActivity.user_id == user_id,
        col(DeletedActivity.start_time) >= start_time - window,
        col(DeletedActivity.start_time) <= start_time + window,
    )).first() is not None  # fmt: skip


def deleted_garmin_ids(session: Session, user_id: int) -> set[int]:
    rows = session.exec(
        select(DeletedActivity.external_key).where(
            DeletedActivity.user_id == user_id, DeletedActivity.source == "garmin"
        )
    ).all()
    return {int(k) for k in rows if k.isdigit()}


def delete_activities(session: Session, user_id: int, ids: list[int]) -> int:
    """
    Borra las actividades de la persona (las ajenas o inexistentes se ignoran).

    Returns:
        Cuántas se han borrado.
    """
    from app.services.plan_service import refresh_match
    from app.services.storage import get_storage

    rows = session.exec(
        select(Activity).where(Activity.user_id == user_id, col(Activity.id).in_(ids[:MAX_BATCH]))
    ).all()
    if not rows:
        return 0
    removed_ids = [a.id for a in rows]
    plans = session.exec(select(PlannedSession).where(col(PlannedSession.activity_id).in_(removed_ids))).all()
    storage = get_storage()
    for a in rows:
        key = str(a.garmin_activity_id) if a.garmin_activity_id else (a.external_id or "")
        session.add(DeletedActivity(user_id=user_id, source="garmin" if a.garmin_activity_id else a.source,
                                    external_key=key, start_time=a.start_time, duration_s=a.duration_s))  # fmt: skip
        raw = session.get(ActivityRaw, a.id)
        if raw is not None and raw.fit_object_key:
            try:
                storage.delete(raw.fit_object_key)
            except Exception:  # noqa: BLE001 - el fichero es secundario
                logger.info("No se pudo borrar el FIT guardado de la actividad %s", a.id)
        session.delete(a)
    session.commit()
    for planned in plans:  # la sesión del plan pierde su actividad: se busca otra del día o queda pendiente
        session.refresh(planned)
        refresh_match(session, planned)
    session.commit()
    try:
        from app.services.zones import refresh_zones

        refresh_zones(session, user_id)
    except Exception:  # noqa: BLE001
        session.rollback()
    return len(rows)
