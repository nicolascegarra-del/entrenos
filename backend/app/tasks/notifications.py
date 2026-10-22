import logging

from sqlmodel import Session

from app.core.db import engine
from app.services.notifications import daily_all
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="notifications.daily")
def daily_task() -> int:
    """Aviso «hoy toca…» a quien le toque a esta hora (se lanza cada 15 minutos; uno al día por persona)."""
    with Session(engine) as session:
        count = daily_all(session)
    logger.info("Avisos de sesión del día: %s", count)
    return count
