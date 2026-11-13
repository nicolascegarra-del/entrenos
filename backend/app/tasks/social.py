"""Amigos en segundo plano: cerrar los duelos vencidos y avisar de los adelantamientos."""

from sqlmodel import Session

from app.core.db import engine
from app.services import social
from app.tasks.celery_app import celery_app


@celery_app.task(name="social.close_duels")
def close_duels_task() -> int:
    """Cada hora: cierra los duelos cuyo último día ya pasó, decide ganador (o empate) y avisa a los dos."""
    with Session(engine) as session:
        return social.close_duels(session)


@celery_app.task(name="social.duel_overtakes")
def duel_overtakes_task() -> int:
    """Cada hora: avisa a quien acaban de adelantar en un duelo en marcha (una vez por adelantamiento)."""
    with Session(engine) as session:
        return social.duel_overtakes(session)
