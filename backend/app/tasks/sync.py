import logging

import redis
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.db import engine
from app.models import SyncRun, SyncStatus, User
from app.services.garmin_client import GarminConnectClient, GarminNotConnectedError, has_tokens
from app.services.storage import get_storage
from app.services.sync_service import run_sync
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
            run = run_sync(session, user_id, source, get_storage(), days=days, max_new=max_new)
            return run.status
    finally:
        lock.release()


@celery_app.task(name="garmin.sync_user")
def sync_user_task(user_id: int, days: int = 7, max_new: int | None = 50) -> str:
    return sync_user(user_id, days, max_new)


@celery_app.task(name="garmin.sync_all")
def sync_all_task() -> dict[int, str]:
    """Tarea periódica (beat): sincroniza a los usuarios con Garmin conectado."""
    with Session(engine) as session:
        user_ids = [u.id for u in session.exec(select(User)).all()]
    return {uid: sync_user(uid) for uid in user_ids if has_tokens(uid)}
