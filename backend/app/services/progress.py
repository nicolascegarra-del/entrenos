"""
Progresión: carga de entrenamiento, fitness/fatiga/forma, volumen semanal,
eficiencia aeróbica y récords. Las funciones de cálculo son puras.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlmodel import Session, col, select

from app.models import Activity, ActivityFeedback, DailyMetric, MetricScope, UserProfile
from app.services.metric_catalog import CATALOG, RECORD_DISTANCES
from app.services.plan_steps import local_day, sport_family
from app.services.profile import age_on, tanaka_hr_max

CTL_DAYS, ATL_DAYS = 42, 7
DEFAULT_HR_REST = 60.0
LTHR_OF_HR_MAX = 0.89  # aproximación habitual de la FC umbral si Garmin no la da
FALLBACK_TSS_PER_HOUR = {"strength": 30.0}
DEFAULT_TSS_PER_HOUR = 50.0
RPE_AT_THRESHOLD = 7.5  # sin FC, un RPE de 7,5 se considera intensidad de umbral (IF = 1)


@dataclass(frozen=True)
class Thresholds:
    lthr: float | None
    hr_rest: float
    hr_max: float | None


def activity_load(activity: Activity, thresholds: Thresholds, rpe: int | None = None) -> float:
    """
    Carga estilo TSS: horas × IF² × 100 (una hora justo en umbral = 100).

    IF sale de la FC (hrTSS: (FC media − reposo) / (umbral − reposo)); si no hay FC
    pero sí RPE, de RPE / 7,5; y si no hay ninguno, se estima por duración y deporte.
    """
    hours = activity.duration_s / 3600
    lthr = thresholds.lthr
    if activity.avg_hr and lthr and lthr > thresholds.hr_rest:
        intensity = (activity.avg_hr - thresholds.hr_rest) / (lthr - thresholds.hr_rest)
        intensity = min(max(intensity, 0.0), 1.5)
        return round(hours * intensity**2 * 100, 1)
    if rpe:
        intensity = min(rpe / RPE_AT_THRESHOLD, 1.4)
        return round(hours * intensity**2 * 100, 1)
    per_hour = FALLBACK_TSS_PER_HOUR.get(sport_family(activity.sport), DEFAULT_TSS_PER_HOUR)
    return round(hours * per_hour, 1)


def fitness_series(loads: dict[date, float], start: date, end: date) -> list[dict]:
    """
    Fitness (CTL), fatiga (ATL) y forma (TSB) por día con medias exponenciales de 42 y 7 días.
    La forma de un día es fitness − fatiga del día anterior (cómo llegas a entrenar).
    """
    if not loads:
        return []
    first = min(min(loads), start)
    ctl = atl = 0.0
    series = []
    day = first
    while day <= end:
        tsb = ctl - atl
        load = loads.get(day, 0.0)
        ctl += (load - ctl) / CTL_DAYS
        atl += (load - atl) / ATL_DAYS
        if day >= start:
            series.append({"day": day, "load": round(load, 1), "ctl": round(ctl, 1), "atl": round(atl, 1),
                           "tsb": round(tsb, 1)})  # fmt: skip
        day += timedelta(days=1)
    return series


def form_label(tsb: float) -> str:
    """Interpretación orientativa de la forma (TSB)."""
    if tsb > 15:
        return "Muy descansado"
    if tsb > 5:
        return "Fresco"
    if tsb >= -10:
        return "Equilibrado"
    if tsb >= -30:
        return "Cargado"
    return "Sobrecarga"


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def weekly_volume(activities: list[Activity], loads: dict[int, float], first_week: date, last_week: date) -> list[dict]:
    """Distancia, tiempo, nº de actividades y carga por semana (lunes), incluidas las semanas vacías."""
    weeks: dict[date, dict] = {}
    week = first_week
    while week <= last_week:
        weeks[week] = {"week": week, "distance_m": 0.0, "duration_s": 0.0, "count": 0, "load": 0.0}
        week += timedelta(days=7)
    for a in activities:
        bucket = weeks.get(week_start(local_day(a.start_time, a.timezone)))
        if bucket is None:
            continue
        bucket["distance_m"] += a.distance_m or 0
        bucket["duration_s"] += a.duration_s
        bucket["count"] += 1
        bucket["load"] += loads.get(a.id, 0.0)
    return [w | {"load": round(w["load"], 1), "distance_m": round(w["distance_m"], 1)} for w in weeks.values()]


def efficiency(activity: Activity) -> float | None:
    """Eficiencia aeróbica: metros por minuto por pulsación (más alto = más rápido a la misma FC)."""
    if sport_family(activity.sport) != "running" or not activity.avg_hr or not activity.distance_m:
        return None
    if activity.duration_s < 600:  # actividades muy cortas son poco representativas
        return None
    speed_m_min = activity.distance_m / (activity.moving_duration_s or activity.duration_s) * 60
    return round(speed_m_min / activity.avg_hr, 3)


def records(activities: list[Activity]) -> list[dict]:
    """
    Mejor marca por distancia y cómo ha ido mejorando (cada vez que se batió el récord).
    `activities` debe venir en orden cronológico.
    """
    labels = {d.key: d.label for d in CATALOG}
    result = []
    for key, distance in RECORD_DISTANCES.items():
        best: dict | None = None
        history = []
        for a in activities:
            value = a.metrics.get(key)
            if value is None:
                continue
            if best is None or value < best["time_s"]:
                best = {"time_s": value, "activity_id": a.id, "day": local_day(a.start_time, a.timezone)}
                history.append(best)
        result.append({"key": key, "label": labels.get(key, key), "distance_m": distance, "best": best,
                       "history": history})  # fmt: skip
    return result


# ─── Consultas ───────────────────────────────────────────────────────────────


def user_activities(session: Session, user_id: int, since: date | None = None) -> list[Activity]:
    query = select(Activity).where(Activity.user_id == user_id)
    if since:
        query = query.where(Activity.start_time >= since - timedelta(days=1))
    return list(session.exec(query.order_by(Activity.start_time)).all())


def user_thresholds(session: Session, user_id: int) -> Thresholds:
    """
    FC umbral (la de un test confirmado de carrera de las últimas 8 semanas; si no, la última que dio
    Garmin o el 89 % de la FC máx.), FC reposo (mediana 30 días) y FC máx. (registrada o de un test).
    """
    from app.services.test_results import active_test, tested_hr_max

    activities = user_activities(session, user_id)
    test = active_test(session, user_id, "running", "lthr")
    lthr = test.results["lthr"] if test else None
    lthr = lthr or next((a.metrics["lthr"] for a in reversed(activities) if a.metrics.get("lthr")), None)
    hr_max = max([a.max_hr for a in activities if a.max_hr] + [tested_hr_max(session, user_id) or 0]) or None
    if hr_max is None:
        # Sin FC máx. registrada: estimación por edad (Tanaka) si el perfil tiene fecha de nacimiento.
        profile = session.get(UserProfile, user_id)
        if profile and profile.birth_date:
            hr_max = tanaka_hr_max(age_on(profile.birth_date, date.today()))
    if lthr is None and hr_max:
        lthr = round(hr_max * LTHR_OF_HR_MAX)
    rests = session.exec(
        select(DailyMetric).where(DailyMetric.user_id == user_id).order_by(col(DailyMetric.day).desc()).limit(30)
    ).all()
    values = [r.metrics["resting_hr"] for r in rests if r.metrics.get("resting_hr")]
    return Thresholds(lthr=lthr, hr_rest=statistics.median(values) if values else DEFAULT_HR_REST, hr_max=hr_max)


def loads_by_day(
    activities: list[Activity], thresholds: Thresholds, rpes: dict[int, int] | None = None
) -> tuple[dict[date, float], dict[int, float]]:
    rpes = rpes or {}
    per_activity = {a.id: activity_load(a, thresholds, rpes.get(a.id)) for a in activities}
    per_day: dict[date, float] = defaultdict(float)
    for a in activities:
        per_day[local_day(a.start_time, a.timezone)] += per_activity[a.id]
    return dict(per_day), per_activity


def user_rpes(session: Session, user_id: int) -> dict[int, int]:
    """RPE registrado por actividad (para estimar la carga de sesiones sin FC)."""
    rows = session.exec(
        select(ActivityFeedback.activity_id, ActivityFeedback.rpe)
        .join(Activity, col(Activity.id) == ActivityFeedback.activity_id)
        .where(Activity.user_id == user_id, col(ActivityFeedback.rpe).is_not(None))
    ).all()
    return dict(rows)


def metric_series(session: Session, user_id: int, key: str, since: date) -> list[dict]:
    """Serie temporal de una métrica del catálogo: diaria (DailyMetric) o de actividad (por día)."""
    definition = next((d for d in CATALOG if d.key == key), None)
    if definition is None:
        return []
    if definition.scope == MetricScope.DAILY:
        rows = session.exec(
            select(DailyMetric)
            .where(DailyMetric.user_id == user_id, DailyMetric.day >= since)
            .order_by(DailyMetric.day)
        ).all()
        return [{"day": r.day, "value": r.metrics[key]} for r in rows if r.metrics.get(key) is not None]
    by_day: dict[date, float] = {}
    for a in user_activities(session, user_id, since):
        if a.metrics.get(key) is not None:
            by_day[local_day(a.start_time, a.timezone)] = a.metrics[key]  # el último del día
    return [{"day": d, "value": v} for d, v in sorted(by_day.items()) if d >= since]
