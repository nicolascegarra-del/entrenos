"""
Sincronización Garmin → BD. Guarda siempre el raw y deriva el modelo normalizado
con `garmin_parser`, de modo que `reprocess_activities` puede rehacerlo entero.
"""

import logging
from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, col, delete, select

from app.models import (
    Activity,
    ActivityRaw,
    ActivityStream,
    DailyMetric,
    Device,
    Lap,
    SyncRun,
    SyncStatus,
)
from app.services import garmin_parser as parser
from app.services.garmin_client import GarminSource
from app.services.storage import ObjectStorage

logger = logging.getLogger(__name__)

PAGE_SIZE = 20


def _known_garmin_ids(session: Session, user_id: int) -> set[int]:
    rows = session.exec(
        select(Activity.garmin_activity_id).where(
            Activity.user_id == user_id, col(Activity.garmin_activity_id).is_not(None)
        )
    )
    return set(rows.all())


def _upsert_device(
    session: Session, user_id: int, garmin_device_id: int | None, names: dict[int, str], seen: datetime
) -> int | None:
    if garmin_device_id is None:
        return None
    device = session.exec(
        select(Device).where(Device.user_id == user_id, Device.garmin_device_id == garmin_device_id)
    ).first()
    if device is None:
        device = Device(
            user_id=user_id,
            garmin_device_id=garmin_device_id,
            name=names.get(garmin_device_id, f"Dispositivo {garmin_device_id}"),
            first_seen=seen,
            last_seen=seen,
        )
        session.add(device)
        session.flush()
    else:
        device.first_seen = min(device.first_seen, seen)
        device.last_seen = max(device.last_seen, seen)
    return device.id


def _apply_raw(session: Session, activity: Activity, raw: ActivityRaw, device_names: dict[int, str]) -> None:
    """Rellena la actividad, sus streams y vueltas a partir de la capa raw (idempotente)."""
    parsed = parser.parse_summary(raw.summary)
    for field in (
        "garmin_activity_id", "sport", "name", "start_time", "timezone", "duration_s", "moving_duration_s",
        "distance_m", "avg_hr", "max_hr", "elevation_gain_m", "calories", "metrics",
    ):  # fmt: skip
        setattr(activity, field, getattr(parsed, field))
    activity.device_id = _upsert_device(
        session, activity.user_id, parsed.garmin_device_id, device_names, parsed.start_time
    )
    session.flush()

    session.exec(delete(ActivityStream).where(col(ActivityStream.activity_id) == activity.id))
    session.exec(delete(Lap).where(col(Lap.activity_id) == activity.id))
    for channel, values in parser.parse_details(raw.details).items():
        session.add(ActivityStream(activity_id=activity.id, channel=channel, values=values))
    for lap in parser.parse_laps(raw.splits, parsed.start_time):
        session.add(Lap(activity_id=activity.id, **lap))
    raw.parser_version = parser.PARSER_VERSION


def import_activity(
    session: Session,
    user_id: int,
    source: GarminSource,
    storage: ObjectStorage,
    summary: dict,
    device_names: dict[int, str],
) -> Activity:
    garmin_id = int(summary["activityId"])
    fit_key = None
    if fit := source.download_fit(garmin_id):
        fit_key = f"fit/{user_id}/{garmin_id}.zip"
        storage.put(fit_key, fit)

    raw = ActivityRaw(
        activity_id=0,  # se asigna tras crear la actividad
        summary=summary,
        details=source.get_activity_details(garmin_id),
        splits=source.get_activity_splits(garmin_id),
        fit_object_key=fit_key,
    )
    activity = Activity(user_id=user_id, sport="other", start_time=datetime.now(UTC), duration_s=0)
    session.add(activity)
    session.flush()
    raw.activity_id = activity.id
    session.add(raw)
    _apply_raw(session, activity, raw, device_names)
    session.commit()
    return activity


def sync_activities(
    session: Session,
    user_id: int,
    source: GarminSource,
    storage: ObjectStorage,
    max_new: int | None = 50,
) -> int:
    """
    Importa las actividades nuevas (de la más reciente hacia atrás).

    Se detiene al encontrar una ya importada, o al llegar a `max_new` (None = todo el
    histórico, para la carga inicial).

    Returns:
        Número de actividades nuevas importadas.
    """
    known = _known_garmin_ids(session, user_id)
    device_names = {
        d["deviceId"]: d.get("productDisplayName") or d.get("displayName") or str(d["deviceId"])
        for d in source.get_devices()
        if d.get("deviceId")
    }
    imported, start = 0, 0
    while max_new is None or imported < max_new:
        page = source.get_activities(start, PAGE_SIZE)
        if not page:
            break
        for summary in page:
            if int(summary["activityId"]) in known:
                return imported
            import_activity(session, user_id, source, storage, summary, device_names)
            imported += 1
            if max_new is not None and imported >= max_new:
                return imported
        start += PAGE_SIZE
    return imported


def sync_daily(session: Session, user_id: int, source: GarminSource, days: int = 7) -> int:
    """Actualiza las métricas diarias de los últimos `days` días (Garmin las corrige a posteriori)."""
    today = date.today()
    for offset in range(days):
        day = today - timedelta(days=offset)
        raw = source.get_daily(day.isoformat())
        row = session.exec(
            select(DailyMetric).where(DailyMetric.user_id == user_id, DailyMetric.day == day)
        ).first() or DailyMetric(user_id=user_id, day=day)
        row.raw = {k: v for k, v in raw.items() if v is not None}
        row.metrics = parser.parse_daily(raw)
        session.add(row)
    session.commit()
    return days


def run_sync(
    session: Session,
    user_id: int,
    source: GarminSource,
    storage: ObjectStorage,
    days: int = 7,
    max_new: int | None = 50,
) -> SyncRun:
    """Sincronización completa registrada en `SyncRun` (estado visible en la web)."""
    run = SyncRun(user_id=user_id)
    session.add(run)
    session.commit()
    try:
        run.new_activities = sync_activities(session, user_id, source, storage, max_new)
        run.daily_days = sync_daily(session, user_id, source, days)
        if run.new_activities:
            from app.services.plan_service import match_pending  # import local: evita ciclo

            match_pending(session, user_id)
        run.status = SyncStatus.SUCCESS
    except Exception as exc:
        session.rollback()
        logger.exception("Error en la sincronización con Garmin")
        run.status = SyncStatus.ERROR
        run.error = f"{type(exc).__name__}: {exc}"[:500]
    run.finished_at = datetime.now(UTC)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def reprocess_activities(session: Session, user_id: int, only_outdated: bool = True) -> int:
    """Re-parsea la capa raw (tras ampliar el catálogo o cambiar el parser)."""
    query = select(Activity, ActivityRaw).join(ActivityRaw).where(Activity.user_id == user_id)
    if only_outdated:
        query = query.where(ActivityRaw.parser_version < parser.PARSER_VERSION)
    count = 0
    for activity, raw in session.exec(query).all():
        _apply_raw(session, activity, raw, {})
        count += 1
    session.commit()
    return count
