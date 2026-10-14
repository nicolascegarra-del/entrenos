"""Fuerza: 1RM estimado, resumen por sesión e historial por ejercicio (funciones puras + consultas)."""

import unicodedata
from collections import defaultdict
from datetime import date

from sqlmodel import Session, col, select

from app.models import Activity, StrengthSet
from app.services.plan_steps import local_day

MAX_REPS_FOR_1RM = 12  # por encima, la estimación de 1RM deja de ser fiable


def exercise_key(name: str) -> str:
    """Clave para agrupar ejercicios: sin tildes, minúsculas y espacios normalizados ("Press Banca" = "press banca")."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().split())


def clean_exercise(name: str) -> str:
    """Nombre a guardar: espacios normalizados y primera letra en mayúscula."""
    text = " ".join(name.split())
    return text[:1].upper() + text[1:]


def estimated_1rm(weight_kg: float | None, reps: int | None) -> float | None:
    """
    1RM estimado con la fórmula de Epley: peso × (1 + reps / 30).

    Returns:
        None si falta peso o repeticiones, o con más de 12 repeticiones.
    """
    if not weight_kg or not reps or reps > MAX_REPS_FOR_1RM:
        return None
    if reps == 1:
        return weight_kg
    return round(weight_kg * (1 + reps / 30), 1)


def summarize_sets(sets: list[StrengthSet]) -> list[dict]:
    """Resumen por ejercicio de una sesión: series, repeticiones, volumen (reps × kg), mejor peso y 1RM."""
    groups: dict[str, list[StrengthSet]] = defaultdict(list)
    labels: dict[str, str] = {}
    for s in sorted(sets, key=lambda s: s.position):
        key = exercise_key(s.exercise)
        groups[key].append(s)
        labels.setdefault(key, s.exercise)
    summary = []
    for key, items in groups.items():
        e1rms = [v for s in items if (v := estimated_1rm(s.weight_kg, s.reps)) is not None]
        weights = [s.weight_kg for s in items if s.weight_kg]
        summary.append(
            {
                "key": key,
                "exercise": labels[key],
                "sets": len(items),
                "reps": sum(s.reps or 0 for s in items),
                "volume_kg": round(sum((s.reps or 0) * (s.weight_kg or 0) for s in items), 1),
                "top_weight_kg": max(weights) if weights else None,
                "best_e1rm_kg": max(e1rms) if e1rms else None,
            }
        )
    return summary


def _sets_with_activity(session: Session, user_id: int) -> list[tuple[StrengthSet, Activity]]:
    return list(
        session.exec(
            select(StrengthSet, Activity)
            .join(Activity, col(Activity.id) == StrengthSet.activity_id)
            .where(Activity.user_id == user_id)
            .order_by(Activity.start_time, StrengthSet.position)
        ).all()
    )


def exercise_history(session: Session, user_id: int) -> dict[str, list[dict]]:
    """Por ejercicio, una entrada por sesión (cronológica) con su resumen."""
    by_activity: dict[int, tuple[Activity, list[StrengthSet]]] = {}
    for s, a in _sets_with_activity(session, user_id):
        by_activity.setdefault(a.id, (a, []))[1].append(s)
    history: dict[str, list[dict]] = defaultdict(list)
    for activity, sets in by_activity.values():
        day: date = local_day(activity.start_time, activity.timezone)
        for item in summarize_sets(sets):
            history[item["key"]].append(item | {"day": day, "activity_id": activity.id})
    return dict(history)


def exercise_overview(history: dict[str, list[dict]]) -> list[dict]:
    """Lista de ejercicios con nº de sesiones, última fecha, mejor 1RM y su variación desde la primera sesión."""
    overview = []
    for key, sessions in history.items():
        e1rms = [s["best_e1rm_kg"] for s in sessions if s["best_e1rm_kg"]]
        overview.append(
            {
                "key": key,
                "exercise": sessions[-1]["exercise"],
                "sessions": len(sessions),
                "last_day": sessions[-1]["day"],
                "best_e1rm_kg": max(e1rms) if e1rms else None,
                "e1rm_change_kg": round(e1rms[-1] - e1rms[0], 1) if len(e1rms) >= 2 else None,
                "last_top_weight_kg": sessions[-1]["top_weight_kg"],
            }
        )
    return sorted(overview, key=lambda e: e["last_day"], reverse=True)
