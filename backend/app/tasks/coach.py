"""Entrenador IA en segundo plano: abrir la revisión del domingo y escribir su resumen."""

from sqlmodel import Session

from app.core.db import engine
from app.services import modules, weekly_review
from app.tasks.celery_app import celery_app


@celery_app.task(name="coach.weekly_tick")
def weekly_tick_task() -> int:
    """Cada hora: el domingo desde las 18:00 locales se abre la revisión y se avisa."""
    with Session(engine) as session:
        return weekly_review.due_tick(session)


@celery_app.task(name="coach.weekly_summary")
def weekly_summary_task(checkin_id: int) -> str:
    with Session(engine) as session:
        from app.models import WeeklyCheckin

        checkin = session.get(WeeklyCheckin, checkin_id)
        if checkin is not None and not modules.enabled(session, "ia", checkin.user_id):
            return "módulo desactivado"
        row = weekly_review.generate(session, checkin_id)
        return row.status if row else "missing"
