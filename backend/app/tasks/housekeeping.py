import logging

from sqlmodel import Session

from app.core.db import engine
from app.core.email import email_enabled
from app.services import accounts, mailer
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="accounts.housekeeping")
def housekeeping_task() -> dict[str, int]:
    """Limpieza diaria: cuentas sin confirmar y cuentas Básicas inactivas (ver accounts.housekeeping)."""
    with Session(engine) as session:
        result = accounts.housekeeping(session, email_enabled(), mailer.send_inactivity_warning)
    logger.info("Mantenimiento de cuentas: %s", result)
    return result
