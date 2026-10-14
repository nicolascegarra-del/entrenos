"""Emparejado plan ↔ actividad y persistencia del cumplimiento."""

from datetime import UTC, date, datetime, time, timedelta

from sqlmodel import Session, col, select

from app.models import Activity, ActivityStream, Lap, MatchMode, PlannedBlock, PlannedSession
from app.services.compliance import compute_compliance
from app.services.plan_steps import estimated_duration_s, expand_steps, local_day, sport_family

_COMPLIANCE_CHANNELS = ["time", "distance", "hr", "power", "cadence"]


def blocks_of(session: Session, planned: PlannedSession) -> list[PlannedBlock]:
    return list(
        session.exec(
            select(PlannedBlock).where(PlannedBlock.session_id == planned.id).order_by(PlannedBlock.position)
        ).all()
    )


def candidate_activities(session: Session, user_id: int, day: date, sport: str) -> list[Activity]:
    """Actividades del mismo día local y misma familia de deporte."""
    start = datetime.combine(day, time.min, tzinfo=UTC) - timedelta(hours=14)
    end = datetime.combine(day, time.max, tzinfo=UTC) + timedelta(hours=14)
    rows = session.exec(
        select(Activity).where(Activity.user_id == user_id, Activity.start_time >= start, Activity.start_time <= end)
    ).all()
    family = sport_family(sport)
    return [a for a in rows if local_day(a.start_time, a.timezone) == day and sport_family(a.sport) == family]


def auto_match(session: Session, planned: PlannedSession) -> Activity | None:
    """La actividad libre del día más parecida en duración a lo planificado."""
    taken = set(
        session.exec(
            select(PlannedSession.activity_id).where(
                PlannedSession.user_id == planned.user_id,
                col(PlannedSession.activity_id).is_not(None),
                PlannedSession.id != planned.id,
            )
        ).all()
    )
    candidates = [
        a for a in candidate_activities(session, planned.user_id, planned.day, planned.sport) if a.id not in taken
    ]
    if not candidates:
        return None
    expected = estimated_duration_s(expand_steps(blocks_of(session, planned)))
    return min(candidates, key=lambda a: abs(a.duration_s - expected))


def recompute(session: Session, planned: PlannedSession) -> None:
    """Recalcula y guarda el cumplimiento (o lo limpia si no hay actividad)."""
    if planned.activity_id is None:
        planned.compliance_score, planned.compliance_detail = None, {}
        session.add(planned)
        return
    laps = [
        lap.model_dump()
        for lap in session.exec(select(Lap).where(Lap.activity_id == planned.activity_id).order_by(Lap.index))
    ]
    streams = session.exec(
        select(ActivityStream).where(
            ActivityStream.activity_id == planned.activity_id,
            col(ActivityStream.channel).in_(_COMPLIANCE_CHANNELS),
        )
    ).all()
    detail = compute_compliance(expand_steps(blocks_of(session, planned)), laps, {s.channel: s.values for s in streams})
    planned.compliance_score, planned.compliance_detail = detail["score"], detail
    session.add(planned)


def refresh_match(session: Session, planned: PlannedSession) -> None:
    """En modo automático vuelve a buscar actividad; en manual respeta la elegida."""
    if planned.match_mode == MatchMode.AUTO:
        match = auto_match(session, planned)
        planned.activity_id = match.id if match else None
    recompute(session, planned)


def match_pending(session: Session, user_id: int) -> int:
    """Tras sincronizar: empareja las sesiones automáticas pasadas que aún no tienen actividad."""
    pending = session.exec(
        select(PlannedSession).where(
            PlannedSession.user_id == user_id,
            col(PlannedSession.activity_id).is_(None),
            PlannedSession.match_mode == MatchMode.AUTO,
            PlannedSession.day <= date.today() + timedelta(days=1),
        )
    ).all()
    matched = 0
    for planned in pending:
        refresh_match(session, planned)
        matched += planned.activity_id is not None
    session.commit()
    return matched
