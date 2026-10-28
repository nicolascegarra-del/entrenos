"""Tareas del anillo Oura: histórico, sincronización periódica, webhooks y suscripciones."""

import logging
from datetime import date, timedelta

from sqlmodel import Session, select

from app.core.db import engine
from app.models import OuraConnection, User, UserStatus
from app.services import limits, oura_sync, oura_webhooks
from app.services.oura_client import OuraAuthError, OuraError
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

HISTORY_DAYS = 90
HISTORY_BLOCK_DAYS = 30
RECENT_DAYS = 3


def history_days(session: Session, user: User) -> int:
    """90 días, o menos si la cuenta Básica tiene un histórico más corto."""
    limit = limits.limits_for(session, user).history_days
    return min(HISTORY_DAYS, limit) if limit else HISTORY_DAYS


def import_history(session: Session, user_id: int, today: date | None = None) -> dict:
    """Importa el histórico en bloques de 30 días (del más reciente al más antiguo) y anota el estado."""
    user, conn = session.get(User, user_id), session.get(OuraConnection, user_id)
    if user is None or conn is None:
        return {}
    today = today or date.today()
    start = today - timedelta(days=history_days(session, user) - 1)
    conn.history_status, conn.history_from, conn.history_to = "running", start, today
    session.add(conn)
    session.commit()
    totals: dict[str, int] = {}
    try:
        block_end = today
        while block_end >= start:
            block_start = max(start, block_end - timedelta(days=HISTORY_BLOCK_DAYS - 1))
            for k, v in oura_sync.sync_range(session, user_id, block_start, block_end).items():
                totals[k] = totals.get(k, 0) + v
            block_end = block_start - timedelta(days=1)
        status = "done"
    except OuraError as exc:
        session.rollback()
        logger.warning("Oura: fallo importando el histórico (%s)", type(exc).__name__)
        status = "error"
        conn = session.get(OuraConnection, user_id)
        if conn is not None and conn.status != "expired":
            conn.status, conn.last_error = "error", str(exc)[:255]
    conn = session.get(OuraConnection, user_id)
    if conn is not None:
        conn.history_status = status
        session.add(conn)
        session.commit()
    return totals


@celery_app.task(name="oura.import_history")
def oura_import_history_task(user_id: int) -> dict:
    with Session(engine) as session:
        return import_history(session, user_id)


def sync_user(session: Session, user_id: int, days: int = RECENT_DAYS) -> dict:
    today = date.today()
    try:
        return oura_sync.sync_range(session, user_id, today - timedelta(days=days - 1), today)
    except OuraAuthError:
        return {}
    except OuraError as exc:
        session.rollback()
        conn = session.get(OuraConnection, user_id)
        if conn is not None:
            conn.status, conn.last_error = "error", str(exc)[:255]
            session.add(conn)
            session.commit()
        return {}


@celery_app.task(name="oura.sync_user")
def oura_sync_user_task(user_id: int) -> dict:
    with Session(engine) as session:
        return sync_user(session, user_id)


def sync_recent(session: Session) -> int:
    """Últimos 3 días a quien tenga Oura conectado (no caducado), la cuenta activa y el módulo encendido."""
    rows = session.exec(
        select(OuraConnection.user_id)
        .join(User, User.id == OuraConnection.user_id)
        .where(OuraConnection.status != "expired", User.status == UserStatus.ACTIVE)
    ).all()
    done = 0
    for uid in rows:
        if oura_sync.oura_enabled(session, uid):
            sync_user(session, uid)
            done += 1
    return done


@celery_app.task(name="oura.sync_recent")
def oura_sync_recent_task() -> int:
    with Session(engine) as session:
        return sync_recent(session)


@celery_app.task(name="oura.fetch_object")
def oura_fetch_object_task(user_id: int, data_type: str, object_id: str, event_type: str = "update") -> int:
    with Session(engine) as session:
        try:
            return oura_sync.fetch_object(session, user_id, data_type, object_id, event_type)
        except OuraError:
            session.rollback()
            return 0


@celery_app.task(name="oura.ensure_subscriptions")
def oura_ensure_subscriptions_task() -> dict:
    with Session(engine) as session:
        return oura_webhooks.ensure_subscriptions(session)
