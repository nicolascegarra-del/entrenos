"""Tareas de Suunto, Amazfit (Zepp), Xiaomi y Samsung: sincronizar, la espera del QR de Xiaomi y la ronda periódica."""

import logging
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core.db import engine
from app.models import DeviceConnection, User, UserStatus
from app.services import devices, modules
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="devices.sync_user")
def device_sync_task(user_id: int, provider: str) -> int:
    with Session(engine) as session:
        return devices.sync(session, user_id, provider)


@celery_app.task(name="devices.xiaomi_wait_qr")
def xiaomi_wait_qr_task(user_id: int) -> str:
    """Espera (hasta ~2 min) a que se apruebe el QR de Xiaomi; si se aprueba, guarda la sesión e importa."""
    from app.services.devices import xiaomi

    with Session(engine) as session:
        conn = devices.get_connection(session, user_id, "xiaomi")
        if conn is None or conn.status != "pending":
            return "skip"
        pending = devices.read_session(conn)
        try:
            sess, account = xiaomi.finish_qr(pending, pending.get("region") or xiaomi.DEFAULT_REGION)
        except devices.DeviceError as exc:
            # Si mientras tanto se pidió otro QR, esta espera ya no cuenta.
            session.refresh(conn)
            if conn.status == "pending" and devices.read_session(conn).get("lp") == pending.get("lp"):
                conn.status, conn.last_error = "error", str(exc)[:255]
                session.add(conn)
                session.commit()
            return "error"
        devices.save_session(session, user_id, "xiaomi", sess, account)
        devices.sync(session, user_id, "xiaomi")
    return "ok"


@celery_app.task(name="devices.sync_all")
def devices_sync_all_task() -> int:
    """
    Quien tenga Suunto, Amazfit, Xiaomi o Samsung conectado (cuenta activa y módulo encendido), cuando le
    toque según Ajustes → Conexiones.
    """
    from app.services.sync_schedule import connection_due

    total = 0
    now = datetime.now(UTC)
    with Session(engine) as session:
        rows = session.exec(
            select(DeviceConnection.user_id, DeviceConnection.provider, DeviceConnection.last_sync_at)
            .join(User, User.id == DeviceConnection.user_id)
            .where(DeviceConnection.status.in_(("ok", "error")), User.status == UserStatus.ACTIVE)
        ).all()
        for uid, provider, last in rows:
            if modules.enabled(session, provider, uid) and connection_due(session, uid, last, now):
                total += devices.sync(session, uid, provider)
    logger.info("Relojes por cuenta de marca: %s actividades nuevas", total)
    return total
