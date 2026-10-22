"""
Límites de las cuentas Básicas (autoregistro): histórico importado de Garmin, objetivos
activos y sesiones planificadas por semana. Las cuentas Completas no tienen límites.
Los valores los ajusta un administrador (Admin → Registro) y se guardan en `AppSetting`.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlmodel import Session, col, func, select

from app.models import AccountTier, PlannedSession, RaceGoal, User
from app.services.accounts import get_setting, set_setting

DEFAULTS = {"basic_history_days": 180, "basic_max_goals": 2, "basic_max_sessions_week": 14}
BOUNDS = {"basic_history_days": (30, 3650), "basic_max_goals": (1, 50), "basic_max_sessions_week": (1, 50)}


@dataclass(frozen=True)
class Limits:
    """None = sin límite."""

    history_days: int | None = None
    max_goals: int | None = None
    max_sessions_week: int | None = None


class QuotaError(Exception):
    """Se ha alcanzado una cuota; el mensaje es apto para mostrar al usuario."""


def basic_limits(session: Session) -> Limits:
    values = {key: int(get_setting(session, key, str(default))) for key, default in DEFAULTS.items()}
    return Limits(values["basic_history_days"], values["basic_max_goals"], values["basic_max_sessions_week"])


def save_basic_limits(session: Session, **values: int) -> dict[str, tuple[int, int]]:
    """
    Guarda los límites recibidos (acotados a BOUNDS).

    Returns:
        Los que han cambiado: {clave: (antes, después)} para la auditoría.
    """
    current = basic_limits(session)
    before = {"basic_history_days": current.history_days, "basic_max_goals": current.max_goals,
              "basic_max_sessions_week": current.max_sessions_week}  # fmt: skip
    changed = {}
    for key, value in values.items():
        low, high = BOUNDS[key]
        value = max(low, min(high, int(value)))
        if value != before[key]:
            set_setting(session, key, str(value))
            changed[key] = (before[key], value)
    return changed


def limits_for(session: Session, user: User) -> Limits:
    return basic_limits(session) if user.tier == AccountTier.BASIC else Limits()


def history_since(session: Session, user: User, today: date | None = None) -> date | None:
    """Primera fecha que se importa de Garmin (None = todo el histórico)."""
    days = limits_for(session, user).history_days
    return None if days is None else (today or date.today()) - timedelta(days=days)


def check_goal_quota(session: Session, user: User, today: date | None = None) -> None:
    """Objetivos activos = con fecha de hoy en adelante y sin resultado."""
    limit = limits_for(session, user).max_goals
    if limit is None:
        return
    active = session.exec(
        select(func.count(col(RaceGoal.id))).where(
            RaceGoal.user_id == user.id,
            RaceGoal.race_date >= (today or date.today()),
            col(RaceGoal.result_time_s).is_(None),
        )
    ).one()
    if active >= limit:
        raise QuotaError(
            f"Tu cuenta Básica permite {limit} objetivos activos. Borra uno o pide a un administrador "
            "que amplíe tu cuenta."
        )


def check_session_quota(session: Session, user: User, day: date, exclude_id: int | None = None) -> None:
    """Sesiones planificadas en la semana (lunes–domingo) de `day`."""
    limit = limits_for(session, user).max_sessions_week
    if limit is None:
        return
    monday = day - timedelta(days=day.weekday())
    query = select(func.count(col(PlannedSession.id))).where(
        PlannedSession.user_id == user.id,
        PlannedSession.day >= monday,
        PlannedSession.day < monday + timedelta(days=7),
    )
    if exclude_id is not None:
        query = query.where(PlannedSession.id != exclude_id)
    if session.exec(query).one() >= limit:
        raise QuotaError(
            f"Tu cuenta Básica permite {limit} sesiones por semana. Pide a un administrador que amplíe tu cuenta."
        )
