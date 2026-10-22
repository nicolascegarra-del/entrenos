"""
Zapatillas (material): kilómetros acumulados, asignación automática de las carreras nuevas a la
zapatilla por defecto e importación del material de Garmin (si la persona lo tiene allí).
"""

import logging
from datetime import date

from sqlmodel import Session, col, func, select

from app.models import Activity, Gear
from app.services.plan_steps import local_day, sport_family

logger = logging.getLogger(__name__)

WARN_MARGIN_KM = 50  # aviso «pronto tocará cambiarlas» a falta de esta distancia


def gear_km(session: Session, gear_ids: list[int]) -> dict[int, float]:
    """Kilómetros de actividades asignadas por zapatilla (sin los iniciales)."""
    if not gear_ids:
        return {}
    rows = session.exec(
        select(Activity.gear_id, func.coalesce(func.sum(Activity.distance_m), 0))
        .where(col(Activity.gear_id).in_(gear_ids))
        .group_by(Activity.gear_id)
    ).all()
    return {gid: round(meters / 1000, 1) for gid, meters in rows}


def gear_status(total_km: float, alert_km: float) -> str:
    """ok | soon (a menos de WARN_MARGIN_KM) | replace (pasada del límite)."""
    if total_km >= alert_km:
        return "replace"
    if total_km >= alert_km - WARN_MARGIN_KM:
        return "soon"
    return "ok"


def list_gear(session: Session, user_id: int, include_retired: bool = True) -> list[dict]:
    query = select(Gear).where(Gear.user_id == user_id)
    if not include_retired:
        query = query.where(~col(Gear.retired))
    rows = session.exec(query.order_by(col(Gear.retired), col(Gear.created_at).desc())).all()
    km = gear_km(session, [g.id for g in rows])
    out = []
    for g in rows:
        total = round(g.start_km + km.get(g.id, 0), 1)
        out.append({
            "id": g.id, "name": g.name, "brand": g.brand, "model": g.model, "sport": g.sport,
            "start_km": g.start_km, "alert_km": g.alert_km, "first_use": g.first_use, "is_default": g.is_default,
            "retired": g.retired, "from_garmin": g.garmin_uuid is not None, "total_km": total,
            "status": "retired" if g.retired else gear_status(total, g.alert_km),
        })  # fmt: skip
    return out


def set_default(session: Session, user_id: int, gear: Gear) -> None:
    for other in session.exec(select(Gear).where(Gear.user_id == user_id, Gear.sport == gear.sport)).all():
        if other.id != gear.id and other.is_default:
            other.is_default = False
            session.add(other)
    gear.is_default = True
    session.add(gear)


def assign_default(session: Session, user_id: int) -> int:
    """
    Asigna a la zapatilla por defecto las carreras sin zapatilla desde su primer uso.
    Se llama tras cada sincronización y al marcar una zapatilla como predeterminada.

    Returns:
        Actividades asignadas.
    """
    default = session.exec(select(Gear).where(Gear.user_id == user_id, Gear.is_default, ~col(Gear.retired))).first()
    if default is None:
        return 0
    since = default.first_use or (default.created_at.date() if default.created_at else date.today())
    count = 0
    for a in session.exec(select(Activity).where(Activity.user_id == user_id, col(Activity.gear_id).is_(None))).all():
        if sport_family(a.sport) == default.sport and local_day(a.start_time, a.timezone) >= since:
            a.gear_id = default.id
            session.add(a)
            count += 1
    session.commit()
    return count


def import_garmin_gear(session: Session, user_id: int, api, profile_number: str) -> int:
    """
    Importa las zapatillas de Garmin Connect (y a qué actividades se asignaron allí).
    Es opcional: si Garmin falla o no hay material, no pasa nada.

    Returns:
        Zapatillas nuevas importadas.
    """
    try:
        items = api.get_gear(profile_number) or []
    except Exception:  # noqa: BLE001 - API no oficial: cualquier fallo se ignora
        logger.warning("No se pudo leer el material de Garmin")
        return 0
    created = 0
    for it in items:
        if (it.get("gearTypeName") or "").lower() not in ("shoes", "zapatillas", "running shoes"):
            continue
        uuid = it.get("uuid")
        if not uuid:
            continue
        gear = session.exec(select(Gear).where(Gear.user_id == user_id, Gear.garmin_uuid == uuid)).first()
        if gear is None:
            gear = Gear(user_id=user_id, garmin_uuid=uuid, name=it.get("displayName") or it.get("customMakeModel")
                        or "Zapatillas de Garmin")  # fmt: skip
            created += 1
        gear.brand = it.get("gearMakeName") or gear.brand
        gear.model = it.get("gearModelName") or gear.model
        if it.get("maximumMeters"):
            gear.alert_km = round(it["maximumMeters"] / 1000)
        gear.retired = (it.get("gearStatusName") or "active").lower() == "retired"
        session.add(gear)
        session.flush()
        try:
            for act in api.get_gear_activities(uuid) or []:
                activity = session.exec(select(Activity).where(
                    Activity.user_id == user_id, Activity.garmin_activity_id == act.get("activityId")
                )).first()  # fmt: skip
                if activity is not None and activity.gear_id is None:
                    activity.gear_id = gear.id
                    session.add(activity)
        except Exception:  # noqa: BLE001
            logger.warning("No se pudieron leer las actividades de una zapatilla de Garmin")
    session.commit()
    return created
