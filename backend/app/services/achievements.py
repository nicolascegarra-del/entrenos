"""
Rachas, logros y retos del mes.

- Logros: hitos fijos (primeros 5/10/21/42 km, km acumulados, nº de entrenos, desnivel acumulado),
  rachas semanales y récords batidos. Se guardan al conseguirse (tabla `achievement`) con el día real.
- Racha: semanas seguidas (lunes–domingo) con al menos N entrenos; la semana en curso no la rompe.
- Retos del mes: objetivos de km, entrenos y desnivel a partir de tu media de los 3 meses anteriores
  (+10 %), así que son personales y no cambian durante el mes.

`evaluate` se llama tras cada sincronización; la primera vez guarda el historial sin avisar.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta

from sqlmodel import Session, select

from app.models import Achievement, Activity
from app.services import notifications
from app.services import progress as prog
from app.services.es_format import num
from app.services.metric_catalog import CATALOG as METRICS
from app.services.plan_steps import local_day, sport_family
from app.services.sync_schedule import get_user_settings

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]  # fmt: skip
NOTIFY_RECENT_DAYS = 14  # no se avisa de logros de actividades antiguas importadas ahora


@dataclass(frozen=True)
class Milestone:
    key: str
    group: str  # single_run | run_km | count | elevation | streak
    threshold: float
    title: str
    description: str


MILESTONES: list[Milestone] = [
    Milestone("first_run", "single_run", 0.5, "Primera carrera", "Tu primera carrera registrada."),
    Milestone("first_5k", "single_run", 5, "Primeros 5 km", "Una carrera de 5 km o más."),
    Milestone("first_10k", "single_run", 10, "Primeros 10 km", "Una carrera de 10 km o más."),
    Milestone("first_half", "single_run", 21.0975, "Primera media maratón", "Una carrera de 21,1 km o más."),
    Milestone("first_marathon", "single_run", 42.195, "Primera maratón", "Una carrera de 42,2 km o más."),
    Milestone("km_100", "run_km", 100, "100 km corriendo", "Kilómetros de carrera acumulados."),
    Milestone("km_500", "run_km", 500, "500 km corriendo", "Kilómetros de carrera acumulados."),
    Milestone("km_1000", "run_km", 1000, "1.000 km corriendo", "Kilómetros de carrera acumulados."),
    Milestone("km_2500", "run_km", 2500, "2.500 km corriendo", "Kilómetros de carrera acumulados."),
    Milestone("km_5000", "run_km", 5000, "5.000 km corriendo", "Kilómetros de carrera acumulados."),
    Milestone("count_10", "count", 10, "10 entrenos", "Entrenamientos registrados (todos los deportes)."),
    Milestone("count_50", "count", 50, "50 entrenos", "Entrenamientos registrados (todos los deportes)."),
    Milestone("count_100", "count", 100, "100 entrenos", "Entrenamientos registrados (todos los deportes)."),
    Milestone("count_250", "count", 250, "250 entrenos", "Entrenamientos registrados (todos los deportes)."),
    Milestone("count_500", "count", 500, "500 entrenos", "Entrenamientos registrados (todos los deportes)."),
    Milestone("elev_1000", "elevation", 1000, "1.000 m de desnivel", "Desnivel positivo acumulado."),
    Milestone("elev_everest", "elevation", 8849, "Un Everest", "8.849 m de desnivel positivo acumulado."),
    Milestone("elev_25000", "elevation", 25000, "25.000 m de desnivel", "Desnivel positivo acumulado."),
    Milestone("streak_4", "streak", 4, "Racha de 4 semanas", "Un mes seguido cumpliendo tu objetivo semanal."),
    Milestone("streak_12", "streak", 12, "Racha de 12 semanas", "Tres meses seguidos cumpliendo tu objetivo."),
    Milestone("streak_26", "streak", 26, "Racha de 26 semanas", "Medio año seguido cumpliendo tu objetivo."),
    Milestone("streak_52", "streak", 52, "Racha de 52 semanas", "Un año entero cumpliendo tu objetivo semanal."),
]
UNITS = {"single_run": "km", "run_km": "km", "count": "entrenos", "elevation": "m", "streak": "semanas"}


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _day(a: Activity) -> date:
    return local_day(a.start_time, a.timezone)


def _is_run(a: Activity) -> bool:
    return sport_family(a.sport) == "running"


def fmt_time(seconds: float) -> str:
    s = round(seconds)
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


# ─── Racha semanal ───────────────────────────────────────────────────────────


def weekly_counts(activities: list[Activity]) -> dict[date, int]:
    counts: dict[date, int] = {}
    for a in activities:
        w = week_start(_day(a))
        counts[w] = counts.get(w, 0) + 1
    return counts


def streaks(counts: dict[date, int], target: int, today: date) -> dict:
    """
    Racha actual y mejor racha (semanas seguidas con al menos `target` entrenos).
    La semana en curso suma si ya cumple, pero no rompe la racha mientras no termine.
    """
    this_week = week_start(today)
    current = 0
    w = this_week if counts.get(this_week, 0) >= target else this_week - timedelta(days=7)
    while counts.get(w, 0) >= target:
        current += 1
        w -= timedelta(days=7)
    best = run = 0
    if counts:
        w = min(counts)
        while w <= this_week:
            run = run + 1 if counts.get(w, 0) >= target else 0
            best = max(best, run)
            w += timedelta(days=7)
    weeks = [{"start": this_week - timedelta(days=7 * i), "count": counts.get(this_week - timedelta(days=7 * i), 0)}
             for i in range(11, -1, -1)]  # fmt: skip
    for wk in weeks:
        wk["ok"] = wk["count"] >= target
    return {"current": current, "best": best, "target": target, "this_week": counts.get(this_week, 0),
            "weeks": weeks}  # fmt: skip


def _streak_reached(counts: dict[date, int], target: int, length: int) -> date | None:
    """Primer domingo en que se alcanzó una racha de `length` semanas (o None)."""
    if not counts:
        return None
    w, run = min(counts), 0
    last = max(counts)
    while w <= last:
        run = run + 1 if counts.get(w, 0) >= target else 0
        if run >= length:
            return w + timedelta(days=6)
        w += timedelta(days=7)
    return None


# ─── Retos del mes ───────────────────────────────────────────────────────────


def _month_start(day: date, back: int = 0) -> date:
    y, m = day.year, day.month - back
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, 1)


def _month_totals(activities: list[Activity], start: date, end: date) -> dict[str, float]:
    acts = [a for a in activities if start <= _day(a) < end]
    return {
        "km": sum((a.distance_m or 0) / 1000 for a in acts if _is_run(a)),
        "sessions": len(acts),
        "elevation": sum(a.elevation_gain_m or 0 for a in acts),
    }


def _ceil_to(value: float, step: int) -> int:
    return int(math.ceil(value / step) * step)


def challenges(activities: list[Activity], today: date) -> list[dict]:
    """Retos del mes en curso con objetivos personales (media de los 3 meses anteriores +10 %)."""
    start = _month_start(today)
    end = _month_start(start + timedelta(days=32))
    prev = [_month_totals(activities, _month_start(today, k), _month_start(today, k - 1)) for k in (3, 2, 1)]
    now = _month_totals(activities, start, end)
    month = MONTHS[today.month - 1]

    def avg(key: str) -> float:
        return sum(p[key] for p in prev) / 3

    out = [
        {"key": "km", "title": f"Kilómetros de {month}", "unit": "km",
         "target": max(20, _ceil_to(avg("km") * 1.1, 10)), "current": round(now["km"], 1)},
        {"key": "sessions", "title": f"Entrenos de {month}", "unit": "entrenos",
         "target": max(8, math.ceil(avg("sessions") * 1.1)), "current": now["sessions"]},
    ]  # fmt: skip
    if avg("elevation") >= 100:
        out.append({"key": "elevation", "title": f"Desnivel de {month}", "unit": "m",
                    "target": _ceil_to(avg("elevation") * 1.1, 100), "current": round(now["elevation"])})  # fmt: skip
    for c in out:
        c["done"] = c["current"] >= c["target"]
        c["month"] = start.strftime("%Y-%m")
        c["ends"] = end - timedelta(days=1)
    return out


# ─── Cálculo de logros ───────────────────────────────────────────────────────


def candidates(activities: list[Activity], weekly_target: int, today: date) -> list[dict]:
    """Todos los logros conseguidos según el historial (cronológico), con su día y actividad."""
    found: dict[str, dict] = {}
    run_km = elevation = 0.0
    by_group = {g: [m for m in MILESTONES if m.group == g] for g in UNITS}

    def hit(m: Milestone, a: Activity) -> None:
        if m.key not in found:
            found[m.key] = {"key": m.key, "kind": "milestone" if m.group != "streak" else "streak",
                            "title": m.title, "description": m.description, "achieved_on": _day(a),
                            "activity_id": a.id}  # fmt: skip

    for count, a in enumerate(activities, start=1):
        elevation += a.elevation_gain_m or 0
        km = (a.distance_m or 0) / 1000
        if _is_run(a):
            run_km += km
            for m in by_group["single_run"]:
                if km >= m.threshold:
                    hit(m, a)
            for m in by_group["run_km"]:
                if run_km >= m.threshold:
                    hit(m, a)
        for m in by_group["count"]:
            if count >= m.threshold:
                hit(m, a)
        for m in by_group["elevation"]:
            if elevation >= m.threshold:
                hit(m, a)

    counts = weekly_counts(activities)
    for m in by_group["streak"]:
        day = _streak_reached(counts, weekly_target, int(m.threshold))
        if day is not None:
            found[m.key] = {"key": m.key, "kind": "streak", "title": m.title, "description": m.description,
                            "achieved_on": min(day, today), "activity_id": None}  # fmt: skip

    labels = {d.key: d.label for d in METRICS}
    for rec in prog.records(activities):
        for improvement in rec["history"][1:]:  # el primero no «bate» nada
            key = f"pr:{rec['key']}:{improvement['activity_id']}"
            found[key] = {"key": key, "kind": "record",
                          "title": f"Récord en {labels.get(rec['key'], rec['key'])}: {fmt_time(improvement['time_s'])}",
                          "description": "Has mejorado tu mejor marca.", "achieved_on": improvement["day"],
                          "activity_id": improvement["activity_id"]}  # fmt: skip

    # Retos de meses ya terminados no se reconstruyen: solo el del mes en curso, al cumplirse.
    for c in challenges(activities, today):
        if c["done"]:
            key = f"challenge:{c['month']}:{c['key']}"
            found[key] = {"key": key, "kind": "challenge", "title": f"Reto cumplido: {c['title'].lower()}",
                          "description": f"{num(c['current'], 1 if c['unit'] == 'km' else 0)} {c['unit']} "
                                         f"(objetivo {num(c['target'])}).",
                          "achieved_on": today, "activity_id": None}  # fmt: skip
    return list(found.values())


def evaluate(session: Session, user_id: int, today: date | None = None, notify: bool = True) -> list[Achievement]:
    """
    Guarda los logros nuevos y avisa de los recientes. La primera vez (sin logros guardados) solo
    guarda el historial, sin notificaciones.

    Returns:
        Los logros nuevos.
    """
    today = today or date.today()
    existing = set(session.exec(select(Achievement.key).where(Achievement.user_id == user_id)).all())
    activities = prog.user_activities(session, user_id)
    # Primera vez con historial: se guarda sin avisar. Una cuenta nueva sí recibe sus primeros logros.
    old_cutoff = today - timedelta(days=NOTIFY_RECENT_DAYS)
    first_time = not existing and any(_day(a) < old_cutoff for a in activities)
    target = get_user_settings(session, user_id).weekly_goal_sessions
    new = [Achievement(user_id=user_id, **c) for c in candidates(activities, target, today) if c["key"] not in existing]
    for a in new:
        session.add(a)
    session.commit()
    if notify and not first_time:
        recent = [a for a in new if a.achieved_on >= old_cutoff]
        if len(recent) == 1:
            a = recent[0]
            notifications.notify(session, user_id, "achievement", f"ach:{a.key}", f"🏆 {a.title}", a.description,
                                 "/logros")  # fmt: skip
        elif recent:
            notifications.notify(session, user_id, "achievement", f"ach:{today.isoformat()}:{len(recent)}",
                                 f"🏆 {len(recent)} logros nuevos", " · ".join(a.title for a in recent[:4]),
                                 "/logros")  # fmt: skip
    return new


def _progress(activities: list[Activity], streak_best: int) -> dict[str, float]:
    runs = [a for a in activities if _is_run(a)]
    return {
        "single_run": max(((a.distance_m or 0) / 1000 for a in runs), default=0),
        "run_km": sum((a.distance_m or 0) / 1000 for a in runs),
        "count": len(activities),
        "elevation": sum(a.elevation_gain_m or 0 for a in activities),
        "streak": streak_best,
    }


def report(session: Session, user_id: int, today: date | None = None) -> dict:
    """Racha, retos del mes, logros conseguidos y el siguiente hito de cada tipo con su progreso."""
    today = today or date.today()
    activities = prog.user_activities(session, user_id)
    target = get_user_settings(session, user_id).weekly_goal_sessions
    streak = streaks(weekly_counts(activities), target, today)
    got = session.exec(select(Achievement).where(Achievement.user_id == user_id)).all()
    got_keys = {a.key for a in got}
    progress = _progress(activities, streak["best"])
    upcoming = []
    for group, unit in UNITS.items():
        nxt = next((m for m in MILESTONES if m.group == group and m.key not in got_keys), None)
        if nxt is not None:
            current = round(progress[group], 1)
            upcoming.append({"key": nxt.key, "group": group, "title": nxt.title, "description": nxt.description,
                             "current": current, "target": nxt.threshold, "unit": unit,
                             "pct": round(min(100, current / nxt.threshold * 100))})  # fmt: skip
    ordered = sorted(got, key=lambda a: (a.achieved_on, a.id or 0), reverse=True)
    return {
        "streak": streak,
        "challenges": challenges(activities, today),
        "achievements": [
            a.model_dump(include={"key", "kind", "title", "description", "achieved_on", "activity_id"}) for a in ordered
        ],  # fmt: skip
        "upcoming": upcoming,
        "milestones": {"unlocked": sum(1 for m in MILESTONES if m.key in got_keys), "total": len(MILESTONES)},
    }
