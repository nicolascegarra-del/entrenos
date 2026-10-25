import logging

from sqlmodel import Session

from app.core.db import engine
from app.services import modules
from app.services.activity_review import generate
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="ai.review_activity")
def review_activity_task(review_id: int) -> str:
    """Escribe el análisis de un entreno con la IA del usuario."""
    with Session(engine) as session:
        from app.models import ActivityReview

        row = session.get(ActivityReview, review_id)
        if row is not None and not modules.enabled(session, "ia", row.user_id):
            return "módulo desactivado"
        review = generate(session, review_id)
    return review.status if review else "no existe"
