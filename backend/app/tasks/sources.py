import logging

from sqlmodel import Session, select

from app.core.db import engine
from app.models import CorosCredential, User, UserStatus
from app.services import coros
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="coros.sync_user")
def coros_sync_task(user_id: int) -> int:
    with Session(engine) as session:
        return coros.sync(session, user_id)


@celery_app.task(name="coros.sync_all")
def coros_sync_all_task() -> int:
    """Sincroniza cada hora a quien tenga COROS conectado (y la cuenta activa)."""
    total = 0
    with Session(engine) as session:
        users = session.exec(
            select(CorosCredential.user_id)
            .join(User, User.id == CorosCredential.user_id)
            .where(CorosCredential.status != "expired", User.status == UserStatus.ACTIVE)
        ).all()
        for uid in users:
            total += coros.sync(session, uid)
    logger.info("COROS: %s actividades nuevas", total)
    return total
