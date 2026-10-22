import logging

from sqlmodel import Session

from app.core.db import engine
from app.services.training_plans import adapt_due
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="plans.adapt_due")
def adapt_plans_task() -> int:
    """Revisa una vez por semana cada plan activo (se lanza a diario; solo actúa si toca)."""
    with Session(engine) as session:
        count = adapt_due(session)
    logger.info("Planes adaptados: %s", count)
    return count
