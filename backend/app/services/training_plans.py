"""
Planes de entrenamiento: crear uno hacia un objetivo, guardarlo como sesiones planificadas y
adaptarlo cada semana según lo cumplido y cómo llega la persona (frescura y carga reciente).
La lógica del plan está en `plan_generator` (funciones puras); aquí van los datos y la BD.
"""

from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, col, delete, select

from app.models import (
    PlannedBlock,
    PlannedSession,
    RaceGoal,
    TrainingPlan,
    TrainingPlanWeek,
    User,
)
from app.services import plan_generator as gen
from app.services import progress as prog
from app.services.insights import acwr_series
from app.services.limits import limits_for
from app.services.plan_steps import local_day, sport_family
from app.services.race_forecast import forecast, training_data
from app.services.race_models import daniels_paces

DEFAULT_VDOT = 30.0  # sin marcas ni VO2max: ritmos prudentes de principiante


class PlanError(Exception):
    """Plan imposible con esos datos (mensaje apto para mostrar)."""


def current_km_week(session: Session, user_id: int, today: date) -> float:
    """Media semanal de km de carrera de las últimas 4 semanas."""
    since = today - timedelta(days=28)
    km = sum(
        (a.distance_m or 0) / 1000
        for a in prog.user_activities(session, user_id)
        if sport_family(a.sport) == "running" and local_day(a.start_time, a.timezone) >= since
    )
    return round(km / 4, 1)


def _inputs(
    session: Session,
    user: User,
    goal_date: date,
    distance_m: float,
    target_time_s: float | None,
    weekdays: list[int],
    long_day: int,
    start: date,
    start_km: float | None = None,
) -> gen.PlanInput:
    activities = prog.user_activities(session, user.id)
    f = forecast(distance_m, training_data(activities, start))
    vdot = f.vdot_current or DEFAULT_VDOT
    race_pace = (target_time_s or f.probable_s or 0) / (distance_m / 1000)
    paces = daniels_paces(vdot)
    if not race_pace:
        race_pace = sum(paces["threshold"]) / 2 * 1.05
    return gen.PlanInput(
        race_date=goal_date, distance_m=distance_m, start=start, weekdays=tuple(sorted(set(weekdays))),
        long_run_weekday=long_day,
        current_km_week=start_km if start_km is not None else current_km_week(session, user.id, start),
        paces=paces, race_pace_s_km=race_pace, max_sessions_week=limits_for(session, user).max_sessions_week,
    )  # fmt: skip


def preview(session: Session, user: User, goal: RaceGoal, weekdays: list[int], long_day: int,
            today: date | None = None) -> list[gen.Week]:  # fmt: skip
    today = today or date.today()
    if goal.race_date <= today:
        raise PlanError("El objetivo ya ha pasado: crea uno con fecha futura.")
    monday = today - timedelta(days=today.weekday())
    inp = _inputs(session, user, goal.race_date, goal.distance_m, goal.target_time_s, weekdays, long_day, monday)
    try:
        return gen.generate(inp)
    except ValueError as exc:
        raise PlanError(str(exc)) from exc


def _save_workouts(session: Session, plan: TrainingPlan, user_id: int, workouts: list[gen.Workout]) -> None:
    for w in workouts:
        planned = PlannedSession(user_id=user_id, day=w.day, sport="running", title=w.title, notes=w.notes,
                                 plan_id=plan.id, session_kind=w.kind)  # fmt: skip
        session.add(planned)
        session.flush()
        for pos, b in enumerate(w.blocks):
            session.add(PlannedBlock(
                session_id=planned.id, position=pos, kind=b.kind, repeat=b.repeat, duration_s=b.duration_s,
                distance_m=b.distance_m, target_metric="pace" if b.pace else None,
                target_min=b.pace[0] if b.pace else None, target_max=b.pace[1] if b.pace else None,
                recovery_duration_s=b.recovery_duration_s,
            ))  # fmt: skip


def active_plan(session: Session, user_id: int) -> TrainingPlan | None:
    return session.exec(
        select(TrainingPlan).where(TrainingPlan.user_id == user_id, TrainingPlan.status == "active")
    ).first()


def _remove_future_sessions(session: Session, plan: TrainingPlan, from_day: date) -> None:
    """Borra las sesiones del plan aún no hechas desde `from_day` (las ya hechas se conservan)."""
    session.exec(delete(PlannedSession).where(
        PlannedSession.plan_id == plan.id, PlannedSession.day >= from_day, col(PlannedSession.activity_id).is_(None)
    ))  # fmt: skip


def cancel(session: Session, plan: TrainingPlan, today: date | None = None) -> None:
    _remove_future_sessions(session, plan, today or date.today())
    plan.status = "cancelled"
    session.add(plan)
    session.commit()


def create(session: Session, user: User, goal: RaceGoal, weekdays: list[int], long_day: int,
           today: date | None = None) -> TrainingPlan:  # fmt: skip
    """Crea el plan (sustituye al activo, si lo hay) y guarda sus sesiones en el calendario."""
    today = today or date.today()
    weeks = preview(session, user, goal, weekdays, long_day, today)
    old = active_plan(session, user.id)
    if old is not None:
        cancel(session, old, today)
    f = forecast(goal.distance_m, training_data(prog.user_activities(session, user.id), today))
    plan = TrainingPlan(user_id=user.id, goal_id=goal.id, start_date=weeks[0].start, race_date=goal.race_date,
                        distance_m=goal.distance_m, weekdays=sorted(set(weekdays)), long_run_weekday=long_day,
                        start_km_week=current_km_week(session, user.id, today), vdot=f.vdot_current)  # fmt: skip
    session.add(plan)
    session.flush()
    for w in weeks:
        session.add(TrainingPlanWeek(plan_id=plan.id, index=w.index, start_date=w.start, phase=w.phase,
                                     target_km=w.target_km, is_recovery=w.is_recovery))  # fmt: skip
        # Las sesiones de días ya pasados de la semana en curso no se crean.
        _save_workouts(session, plan, user.id, [x for x in w.workouts if x.day >= today])
    session.commit()
    session.refresh(plan)
    return plan


def _week_status(session: Session, plan: TrainingPlan, start: date) -> tuple[float | None, float | None]:
    """Sesiones hechas / planificadas y cumplimiento medio en la semana que empieza en `start`."""
    rows = session.exec(select(PlannedSession).where(
        PlannedSession.plan_id == plan.id, PlannedSession.day >= start, PlannedSession.day < start + timedelta(days=7)
    )).all()  # fmt: skip
    if not rows:
        return None, None
    done = [r for r in rows if r.activity_id]
    scores = [r.compliance_score for r in done if r.compliance_score is not None]
    return len(done) / len(rows), (sum(scores) / len(scores) if scores else None)


def _freshness(session: Session, user_id: int, today: date) -> tuple[float | None, float | None]:
    activities = prog.user_activities(session, user_id)
    thresholds = prog.user_thresholds(session, user_id)
    per_day, _ = prog.loads_by_day(activities, thresholds, prog.user_rpes(session, user_id))
    series = prog.fitness_series(per_day, today, today)
    acwr = acwr_series(per_day, today, today)
    return (series[-1]["tsb"] if series else None), (acwr[-1]["acwr"] if acwr else None)


def adapt(session: Session, plan: TrainingPlan, today: date | None = None) -> dict | None:
    """
    Revisa la semana que acaba de terminar y ajusta la que empieza (volumen, calidad y ritmos actuales).

    Returns:
        El ajuste aplicado ({action, reason, week}) o None si no hay semana que ajustar.
    """
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    week = session.exec(select(TrainingPlanWeek).where(
        TrainingPlanWeek.plan_id == plan.id, TrainingPlanWeek.start_date == monday
    )).first()  # fmt: skip
    if week is None or week.phase == "taper" and week.start_date + timedelta(days=7) > plan.race_date:
        return None  # sin semana en curso o semana de carrera: no se toca
    done_ratio, compliance = _week_status(session, plan, monday - timedelta(days=7))
    tsb, acwr = _freshness(session, plan.user_id, today)
    adj = gen.adjustment(done_ratio, compliance, tsb, acwr)
    user = session.get(User, plan.user_id)
    previous = session.exec(select(TrainingPlanWeek).where(
        TrainingPlanWeek.plan_id == plan.id, TrainingPlanWeek.index == week.index - 1
    )).first()  # fmt: skip
    planned_km = week.target_km
    if adj.action == "hold" and previous is not None:
        planned_km = min(week.target_km, previous.target_km)
    target_km = round(planned_km * adj.factor, 1)
    goal = session.get(RaceGoal, plan.goal_id) if plan.goal_id else None
    inp = _inputs(session, user, plan.race_date, plan.distance_m, goal.target_time_s if goal else None,
                  plan.weekdays, plan.long_run_weekday, monday)  # fmt: skip
    gweek = gen.Week(index=week.index, start=week.start_date, phase=week.phase, target_km=target_km,
                     is_recovery=week.is_recovery or adj.action == "reduce")  # fmt: skip
    workouts = [w for w in gen.week_workouts(gweek, inp) if w.day >= today]
    _remove_future_sessions(session, plan, today)  # solo esta semana: se regenera abajo
    _save_workouts(session, plan, plan.user_id, workouts)
    # Las semanas siguientes se regeneran también para que usen los ritmos actuales.
    later = session.exec(select(TrainingPlanWeek).where(
        TrainingPlanWeek.plan_id == plan.id, TrainingPlanWeek.index > week.index
    ).order_by(TrainingPlanWeek.index)).all()  # fmt: skip
    for lw in later:
        g = gen.Week(index=lw.index, start=lw.start_date, phase=lw.phase, target_km=lw.target_km,
                     is_recovery=lw.is_recovery)  # fmt: skip
        _save_workouts(session, plan, plan.user_id, gen.week_workouts(g, inp))
    week.target_km = target_km
    week.adjustment = {"action": adj.action, "reason": adj.reason, "at": today.isoformat()}
    plan.last_adapted_at = datetime.now(UTC)
    session.add(week)
    session.add(plan)
    session.commit()
    return {"action": adj.action, "reason": adj.reason, "week": week.index}


def adapt_due(session: Session, today: date | None = None) -> int:
    """Adapta los planes activos que aún no se han revisado esta semana (lo llama Celery a diario)."""
    today = today or date.today()
    monday = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time(), tzinfo=UTC)
    count = 0
    for plan in session.exec(select(TrainingPlan).where(TrainingPlan.status == "active")).all():
        if plan.race_date < today:
            plan.status = "done"
            session.add(plan)
            session.commit()
            continue
        due = plan.last_adapted_at is None or plan.last_adapted_at < monday
        if due and adapt(session, plan, today) is not None:
            count += 1
    return count


def report(session: Session, plan: TrainingPlan, today: date | None = None) -> dict:
    """Plan con sus semanas, km planificados vs hechos y el último ajuste."""
    today = today or date.today()
    weeks = session.exec(
        select(TrainingPlanWeek).where(TrainingPlanWeek.plan_id == plan.id).order_by(TrainingPlanWeek.index)
    ).all()
    activities = [a for a in prog.user_activities(session, plan.user_id) if sport_family(a.sport) == "running"]
    goal = session.get(RaceGoal, plan.goal_id) if plan.goal_id else None
    out_weeks = []
    for w in weeks:
        end = w.start_date + timedelta(days=7)
        done_km = sum((a.distance_m or 0) / 1000 for a in activities
                      if w.start_date <= local_day(a.start_time, a.timezone) < end)  # fmt: skip
        sessions = session.exec(select(PlannedSession).where(
            PlannedSession.plan_id == plan.id, PlannedSession.day >= w.start_date, PlannedSession.day < end
        ).order_by(PlannedSession.day)).all()  # fmt: skip
        out_weeks.append({
            "index": w.index, "start": w.start_date.isoformat(), "phase": w.phase,
            "phase_label": gen.PHASE_LABEL[w.phase], "target_km": w.target_km, "done_km": round(done_km, 1),
            "is_recovery": w.is_recovery, "is_current": w.start_date <= today < end,
            "adjustment": w.adjustment or None,
            "sessions": [{"id": s.id, "day": s.day.isoformat(), "title": s.title, "kind": s.session_kind,
                          "done": s.activity_id is not None, "compliance": s.compliance_score} for s in sessions],
        })  # fmt: skip
    current = next((w for w in out_weeks if w["is_current"]), None)
    return {
        "id": plan.id, "status": plan.status, "goal_id": plan.goal_id, "goal_name": goal.name if goal else None,
        "race_date": plan.race_date.isoformat(), "distance_m": plan.distance_m, "weekdays": plan.weekdays,
        "long_run_weekday": plan.long_run_weekday, "vdot": plan.vdot, "weeks": out_weeks,
        "current_week": current["index"] if current else None, "total_weeks": len(out_weeks),
    }  # fmt: skip


def preview_out(weeks: list[gen.Week]) -> list[dict]:
    return [
        {"index": w.index, "start": w.start.isoformat(), "phase": w.phase, "phase_label": gen.PHASE_LABEL[w.phase],
         "target_km": w.target_km, "is_recovery": w.is_recovery,
         "sessions": [{"day": x.day.isoformat(), "title": x.title, "kind": x.kind, "km": x.km} for x in w.workouts]}
        for w in weeks
    ]  # fmt: skip
