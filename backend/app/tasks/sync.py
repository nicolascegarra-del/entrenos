import logging
from datetime import UTC, datetime

import redis
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.db import engine
from app.models import SyncRun, SyncStatus, User, UserStatus
from app.services.garmin_client import GarminConnectClient, GarminNotConnectedError, has_tokens
from app.services.gear import assign_default as assign_default_gear
from app.services.gear import import_garmin_gear
from app.services.limits import history_since
from app.services.profile import apply_garmin_profile
from app.services.storage import get_storage
from app.services.sync_schedule import get_user_settings, is_due, last_run_start
from app.services.sync_service import run_sync
from app.services.zones import refresh_zones
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_S = 30 * 60


def _lock(user_id: int):
    # Evita dos sincronizaciones simultáneas (beat + botón "sincronizar").
    client = redis.Redis.from_url(get_settings().redis_url)
    return client.lock(f"garmin-sync:{user_id}", timeout=LOCK_TIMEOUT_S, blocking=False)


def sync_user(user_id: int, days: int = 7, max_new: int | None = 50) -> str:
    lock = _lock(user_id)
    if not lock.acquire():
        return "en curso"
    try:
        with Session(engine) as session:
            try:
                source = GarminConnectClient(user_id)
            except GarminNotConnectedError as exc:
                session.add(SyncRun(user_id=user_id, status=SyncStatus.ERROR, error=str(exc)[:500]))
                session.commit()
                return "no conectado"
            user = session.get(User, user_id)
            since = history_since(session, user) if user else None  # cuentas Básicas: histórico limitado
            run = run_sync(session, user_id, source, get_storage(), days=days, max_new=max_new, since=since)
            if run.status == SyncStatus.SUCCESS:
                source.persist()  # Garmin renueva los tokens durante el uso
                # Mantiene el perfil (y el historial de peso) al día sin pisar lo editado a mano.
                garmin_profile = source.get_user_profile() or {}
                apply_garmin_profile(session, user_id, garmin_profile)
                refresh_zones(session, user_id)  # umbral nuevo → zonas nuevas (con historial)
                profile_id = garmin_profile.get("id")
                if profile_id:
                    import_garmin_gear(session, user_id, source._api, str(profile_id))  # opcional
                assign_default_gear(session, user_id)  # carreras nuevas → zapatilla por defecto
            return run.status
    finally:
        lock.release()


@celery_app.task(name="garmin.sync_user")
def sync_user_task(user_id: int, days: int = 7, max_new: int | None = 50) -> str:
    return sync_user(user_id, days, max_new)


def users_due(now: datetime) -> list[int]:
    """Usuarios con Garmin conectado, en modo automático y cuyo intervalo ya ha pasado."""
    with Session(engine) as session:
        return [
            u.id
            for u in session.exec(select(User).where(User.status == UserStatus.ACTIVE)).all()
            if has_tokens(u.id) and is_due(get_user_settings(session, u.id), last_run_start(session, u.id), now)
        ]


@celery_app.task(name="garmin.sync_all")
def sync_all_task() -> dict[int, str]:
    """Tarea periódica (beat cada pocos minutos): sincroniza a quien le toque según sus Ajustes."""
    return {uid: sync_user(uid) for uid in users_due(datetime.now(UTC))}
