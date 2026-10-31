"""Tareas de Suunto, Amazfit (Zepp) y Xiaomi: sincronizar, la espera del QR de Xiaomi y la ronda periódica."""

import logging

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
    """Cada 6 h: quien tenga Suunto, Amazfit o Xiaomi conectado (cuenta activa y módulo encendido)."""
    total = 0
    with Session(engine) as session:
        rows = session.exec(
            select(DeviceConnection.user_id, DeviceConnection.provider)
            .join(User, User.id == DeviceConnection.user_id)
            .where(DeviceConnection.status.in_(("ok", "error")), User.status == UserStatus.ACTIVE)
        ).all()
        for uid, provider in rows:
            if modules.enabled(session, provider, uid):
                total += devices.sync(session, uid, provider)
    logger.info("Relojes por cuenta de marca: %s actividades nuevas", total)
    return total
