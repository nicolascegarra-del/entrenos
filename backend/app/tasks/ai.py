import logging

from sqlmodel import Session

from app.core.db import engine
from app.services.activity_review import generate
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="ai.review_activity")
def review_activity_task(review_id: int) -> str:
    """Escribe el análisis de un entreno con la IA del usuario."""
    with Session(engine) as session:
        review = generate(session, review_id)
    return review.status if review else "no existe"
