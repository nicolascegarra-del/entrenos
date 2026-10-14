"""Cuándo toca sincronizar a cada usuario según sus preferencias (modo e intervalo)."""

from datetime import datetime, timedelta

from sqlmodel import Session, col, select

from app.models import SyncMode, SyncRun, UserSettings

# Cada cuánto despierta el beat para comprobar si a alguien le toca (minutos).
TICK_MIN = 5


def get_user_settings(session: Session, user_id: int) -> UserSettings:
    """Preferencias del usuario, o las de por defecto si nunca las ha guardado."""
    return session.get(UserSettings, user_id) or UserSettings(user_id=user_id)


def last_run_start(session: Session, user_id: int) -> datetime | None:
    return session.exec(
        select(SyncRun.started_at).where(SyncRun.user_id == user_id).order_by(col(SyncRun.started_at).desc())
    ).first()


def next_sync_at(settings: UserSettings, last_start: datetime | None, now: datetime) -> datetime | None:
    """Próxima sincronización automática (None en modo manual). Si ya toca, devuelve `now`."""
    if settings.sync_mode == SyncMode.MANUAL:
        return None
    if last_start is None:
        return now
    return max(last_start + timedelta(minutes=settings.sync_interval_min), now)


def is_due(settings: UserSettings, last_start: datetime | None, now: datetime) -> bool:
    """
    ¿Toca sincronizar ya? Se resta medio tick de margen para que un intervalo de
    30 min no acabe ejecutándose cada 35 por el desfase del beat.
    """
    if settings.sync_mode == SyncMode.MANUAL:
        return False
    if last_start is None:
        return True
    return now - last_start >= timedelta(minutes=settings.sync_interval_min - TICK_MIN / 2)
