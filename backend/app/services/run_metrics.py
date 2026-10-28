"""
Indicadores de una carrera que se calculan con cualquier reloj (FC, distancia y altitud):

- **Ritmo ajustado a pendiente (GAP):** el ritmo equivalente en llano, con el coste de subir y bajar de
  `race_day.grade_factor` (modelo de Minetti simplificado).
- **Eficiencia de carrera:** velocidad (m/min) por pulsación, como `progress.efficiency`, comparada con la
  media de tus carreras de los 60 días anteriores.
- **Condición de rendimiento:** la del reloj (Garmin, −20 a +20) si viene en el stream; si no, una estimación
  con la eficiencia de los minutos 6–20 frente a tu referencia (mismo rango y sentido).
- **Carga y esfuerzo:** carga de la sesión (la del reloj o hrTSS), intensidad frente al umbral y una
  recuperación orientativa por bandas de carga.

Funciones puras salvo `summary`, que consulta las carreras anteriores para la referencia.
"""

import math
from datetime import timedelta

from sqlmodel import Session, col, select

from app.models import Activity
from app.services.race_day import grade_factor

GAP_STEP_M = 25.0  # tramos de ~25 m para la pendiente (el ruido de la altitud se suaviza)
BASELINE_DAYS = 60
MIN_BASELINE_RUNS = 3
CONDITION_FROM_S, CONDITION_TO_S = 360, 1200  # Garmin la calcula entre los 6 y los 20 min
CONDITION_RANGE = 20
MAX_SERIES_POINTS = 240


def gap_factor(dist: list, alt: list) -> float | None:
    """Factor medio de coste por pendiente de un tramo (>1 = cuesta más que en llano). None sin altitud."""
    pts = [(d, a) for d, a in zip(dist, alt, strict=False) if d is not None and a is not None]
    if len(pts) < 2 or pts[-1][0] - pts[0][0] <= 0:
        return None
    weighted, total = 0.0, 0.0
    d0, a0 = pts[0]
    for d, a in pts[1:]:
        length = d - d0
        if length < GAP_STEP_M:
            continue
        weighted += length * grade_factor((a - a0) / length)
        total += length
        d0, a0 = d, a
    return weighted / total if total else None


def gap_pace(pace_s_km: float, factor: float | None) -> int | None:
    """Ritmo en llano equivalente: si el tramo costaba un 10 % más, en llano irías un 10 % más rápido."""
    return round(pace_s_km / factor) if factor else None


def efficiency_index(distance_m: float, seconds: float, avg_hr: float | None) -> float | None:
    """Metros por minuto por pulsación (más alto = más rápido a la misma FC)."""
    if not avg_hr or seconds <= 0 or distance_m <= 0:
        return None
    return round(distance_m / seconds * 60 / avg_hr, 3)


def window_efficiency(time: list, dist: list, hr: list, start_s: float, end_s: float) -> float | None:
    """Eficiencia entre dos instantes (segundos desde la salida)."""
    pts = [(t, d, hr[i]) for i, (t, d) in enumerate(zip(time, dist, strict=False))
           if t is not None and d is not None and i < len(hr) and hr[i]]  # fmt: skip
    if not pts:
        return None
    t0 = pts[0][0]
    win = [p for p in pts if start_s <= p[0] - t0 <= end_s]
    if len(win) < 5:
        return None
    return efficiency_index(win[-1][1] - win[0][1], win[-1][0] - win[0][0], sum(p[2] for p in win) / len(win))


def _sample(points: list[list[float]]) -> list[list[float]]:
    step = max(1, math.ceil(len(points) / MAX_SERIES_POINTS))
    return points[::step]


def performance_condition(time: list, watch: list | None, est_ef: float | None,
                          baseline: float | None) -> dict | None:  # fmt: skip
    """
    Condición de rendimiento: la del reloj si la hay (valor inicial a los 6–20 min, final, mínimo y curva);
    si no, la estimada con la eficiencia de los minutos 6–20 frente a tu referencia.
    """
    if watch and any(v is not None for v in watch):
        pts = [(t, v) for t, v in zip(time, watch, strict=False) if t is not None and v is not None]
        if pts:
            t0 = time[0] or 0
            early = [v for t, v in pts if CONDITION_FROM_S <= t - t0 <= CONDITION_TO_S] or [pts[0][1]]
            return {"source": "reloj", "initial": round(early[0]), "final": round(pts[-1][1]),
                    "min": round(min(v for _, v in pts)),
                    "series": _sample([[round(t - t0), round(v)] for t, v in pts])}  # fmt: skip
    if est_ef and baseline:
        pct = (est_ef / baseline - 1) * 100
        value = max(-CONDITION_RANGE, min(CONDITION_RANGE, round(pct)))
        return {"source": "estimado", "initial": value, "final": None, "min": None, "series": []}
    return None


def recovery_hours(load: float) -> tuple[int, int]:
    """Recuperación orientativa (horas) por bandas de carga de la sesión (estilo TSS)."""
    if load < 50:
        return (12, 24)
    if load < 150:
        return (24, 48)
    if load < 300:
        return (48, 72)
    return (72, 96)


def baseline_efficiency(session: Session, activity: Activity) -> tuple[float | None, int]:
    """Media de eficiencia de tus carreras de los 60 días anteriores (sin esta). Returns: (media, n)."""
    from app.services.plan_steps import sport_family
    from app.services.progress import efficiency

    since = activity.start_time - timedelta(days=BASELINE_DAYS)
    rows = session.exec(
        select(Activity).where(
            Activity.user_id == activity.user_id,
            col(Activity.start_time) >= since,
            col(Activity.start_time) < activity.start_time,
            col(Activity.id) != activity.id,
        )
    ).all()
    values = [v for a in rows if sport_family(a.sport) == "running" and (v := efficiency(a)) is not None]
    if len(values) < MIN_BASELINE_RUNS:
        return None, len(values)
    return round(sum(values) / len(values), 3), len(values)


def summary(session: Session, activity: Activity, streams: dict[str, list], splits: list[dict],
            load: float) -> dict:  # fmt: skip
    """Eficiencia, condición, GAP de toda la carrera y carga. Las partes sin datos van a None."""
    from app.services.progress import efficiency

    time, dist, hr, alt = (streams.get(k) or [] for k in ("time", "distance", "hr", "altitude"))
    ef = efficiency(activity)
    baseline, n = baseline_efficiency(session, activity) if ef is not None else (None, 0)
    eff = None
    if ef is not None:
        eff = {"value": ef, "baseline": baseline, "baseline_runs": n,
               "delta_pct": round((ef / baseline - 1) * 100, 1) if baseline else None,
               "by_km": [{"km": s["km"], "value": efficiency_index(s["distance_m"], s["seconds"], s["avg_hr"])}
                         for s in splits]}  # fmt: skip
    early = window_efficiency(time, dist, hr, CONDITION_FROM_S, CONDITION_TO_S) if dist and hr else None
    condition = performance_condition(time, streams.get("performance_condition"), early, baseline)

    gap = None
    factor = gap_factor(dist, alt) if dist and alt else None
    moving = activity.moving_duration_s or activity.duration_s
    if factor and activity.distance_m and moving:
        pace = moving / activity.distance_m * 1000
        gap = {"pace_s_km": round(pace), "gap_s_km": gap_pace(pace, factor), "factor": round(factor, 3)}

    return {"efficiency": eff, "performance_condition": condition, "gap": gap, "load": session_load(activity, load)}


def empty(activity: Activity, load: float) -> dict:
    """Actividades que no son de carrera: solo la carga."""
    return {"efficiency": None, "performance_condition": None, "gap": None, "load": session_load(activity, load)}


def session_load(activity: Activity, load: float) -> dict:
    """Carga de la sesión (hrTSS de KTrain y la del reloj), intensidad frente al umbral y recuperación."""
    hours = activity.duration_s / 3600
    watch_load = (activity.metrics or {}).get("training_load")
    intensity = math.sqrt(load / (hours * 100)) if hours > 0 and load > 0 else None
    low, high = recovery_hours(load)
    return {"load": round(load, 1), "watch_load": watch_load, "intensity": round(intensity, 2) if intensity else None,
            "recovery_h": [low, high]}  # fmt: skip
