"""
Resultados de tests confirmados que mandan sobre Garmin y las estimaciones (umbral, FC máx).

Módulo aparte y sin dependencias de servicios para que `progress` y `zones` lo puedan usar sin ciclos.
"""

from datetime import date, timedelta

from sqlmodel import Session, col, select

from app.models import PerformanceTest
from app.services.plan_steps import sport_family

TEST_VALID_DAYS = 56  # 8 semanas: después vuelve a mandar lo más reciente (Garmin o estimaciones)


def active_test(
    session: Session, user_id: int, sport: str, key: str, today: date | None = None
) -> PerformanceTest | None:
    """El test confirmado más reciente (y aún vigente) de ese deporte que da el valor `key`."""
    today = today or date.today()
    family = sport_family(sport)
    rows = session.exec(
        select(PerformanceTest)
        .where(
            PerformanceTest.user_id == user_id,
            PerformanceTest.status == "confirmed",
            col(PerformanceTest.test_date) >= today - timedelta(days=TEST_VALID_DAYS),
            col(PerformanceTest.test_date) <= today,
        )
        .order_by(col(PerformanceTest.test_date).desc(), col(PerformanceTest.id).desc())
    ).all()
    return next((t for t in rows if sport_family(t.sport) == family and t.results.get(key) is not None), None)


def tested_hr_max(session: Session, user_id: int) -> float | None:
    """La FC máx. más alta de cualquier test confirmado (no caduca: la FC máx. apenas cambia)."""
    rows = session.exec(
        select(PerformanceTest).where(PerformanceTest.user_id == user_id, PerformanceTest.status == "confirmed")
    ).all()
    return max((t.results["hr_max"] for t in rows if t.results.get("hr_max")), default=None)
