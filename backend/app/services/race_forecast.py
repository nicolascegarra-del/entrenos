"""
Previsión de carrera para un objetivo: combina Riegel personal, VDOT de Daniels y
Tanda (maratón), calcula un rango, avisa de su fiabilidad, evalúa la preparación
y se calibra con las carreras reales ya disputadas.
"""

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlmodel import Session, col, select

from app.models import Activity, RaceGoal
from app.services import progress as prog
from app.services.es_format import num
from app.services.metric_catalog import RECORD_DISTANCES
from app.services.plan_steps import local_day, sport_family
from app.services.profile import age_grade, age_on, get_profile
from app.services.race_models import (
    daniels_paces,
    personal_exponent,
    riegel,
    tanda_marathon_s,
    time_for_vdot,
    vdot,
)

MARATHON_M = 42195.0
HALF_M = 21097.5
# Incertidumbre mínima por distancia (fracción del tiempo): crece con la distancia.
BASE_UNCERTAINTY = ((5000, 0.02), (10000, 0.03), (HALF_M, 0.04), (MARATHON_M, 0.06))
TRAINING_MARKS_EXTRA = 0.03  # los mejores tramos de entrenamiento infravaloran lo que harías en carrera
CALIBRATION_BOUNDS = (0.9, 1.1)
# Mejora realista del VDOT: ~1 punto cada 4 semanas (Daniels revisa el VDOT cada 4–6 semanas).
VDOT_GAIN_PER_WEEK = 0.25
TANDA_MIN_KM_WEEK = 30  # por debajo, Tanda da tiempos sin sentido (fuera de su rango de validación)

# Preparación orientativa por distancia: tirada más larga (km) y km/semana medios en 8 semanas.
READINESS = ((5000, 8, 20), (10000, 12, 30), (HALF_M, 18, 40), (MARATHON_M, 30, 55))


@dataclass
class ModelResult:
    key: str
    label: str
    time_s: float
    weight: float
    detail: str


@dataclass
class Forecast:
    probable_s: float | None
    optimistic_s: float | None
    conservative_s: float | None
    models: list[ModelResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    vdot_current: float | None = None
    vdot_source: str | None = None
    exponent: float | None = None
    exponent_personal: bool = False
    calibration_factor: float | None = None
    # Marca de referencia usada (para explicar la previsión).
    source_distance_m: float | None = None
    source_time_s: float | None = None
    source_day: date | None = None
    spread_pct: float | None = None


@dataclass
class TrainingData:
    """Lo que necesitan los modelos, calculado a una fecha (`as_of`) para poder ver la evolución."""

    efforts: dict[str, tuple[float, float, date]]  # clave récord → (distancia, tiempo, día)
    vo2max: float | None
    km_per_week: float  # carrera, media de 8 semanas
    avg_pace_s_km: float | None  # ritmo medio de carrera en 8 semanas
    longest_run_m: float  # tirada más larga en 12 semanas


# ─── Cálculo puro ────────────────────────────────────────────────────────────


def base_uncertainty(distance_m: float) -> float:
    for limit, pct in BASE_UNCERTAINTY:
        if distance_m <= limit * 1.02:
            return pct
    return 0.10


def model_weights(distance_m: float, has_tanda: bool) -> dict[str, float]:
    """Pesos por distancia: en maratón, Tanda (basado en el entrenamiento) gana peso."""
    if has_tanda and abs(distance_m - MARATHON_M) < 1000:
        return {"riegel": 0.3, "vdot": 0.3, "tanda": 0.4}
    return {"riegel": 0.5, "vdot": 0.5}


def forecast(
    distance_m: float, data: TrainingData, calibration: float | None = None, recent_days: int = 180
) -> Forecast:
    """
    Combina los modelos disponibles y devuelve el rango.

    Rango = ± el mayor entre la incertidumbre base de la distancia y la mitad de la
    dispersión entre modelos; se amplía con los avisos de baja fiabilidad.
    """
    result = Forecast(None, None, None)
    if not data.efforts and data.vo2max is None:
        result.warnings.append("No hay marcas recientes ni VO2max: sincroniza carreras para poder prever.")
        return result

    exponent, personal = personal_exponent([(d, t) for d, t, _ in data.efforts.values()])
    result.exponent, result.exponent_personal = round(exponent, 3), personal

    # Marca de referencia: la de mayor VDOT (≥ 3 km) de los últimos `recent_days`.
    newest = max((day for _, _, day in data.efforts.values()), default=None)
    candidates = [
        (vdot(d, t), d, t, day)
        for d, t, day in data.efforts.values()
        if d >= 3000 and newest and (newest - day).days <= recent_days
    ]
    source = max(candidates, default=None)
    models: list[ModelResult] = []
    if source:
        v, d, t, day = source
        result.vdot_current, result.vdot_source = round(v, 1), "marca"
        result.source_distance_m, result.source_time_s, result.source_day = d, t, day
        km = num(d / 1000, 1).removesuffix(",0")
        label = "Riegel (exponente personal)" if personal else "Riegel"
        detail = f"Desde {km} km en {_clock(t)} con exponente {num(exponent, 3)}"
        models.append(ModelResult("riegel", label, riegel(t, d, distance_m, exponent), 0, detail))
        models.append(ModelResult("vdot", "VDOT de Daniels", time_for_vdot(distance_m, v), 0, f"VDOT {num(v, 1)}"))
    elif data.vo2max:
        # Sin marcas: el VO2max estimado por el reloj como aproximación al VDOT.
        result.vdot_current, result.vdot_source = data.vo2max, "vo2max"
        models.append(ModelResult("vdot", "VDOT (desde VO2max del reloj)", time_for_vdot(distance_m, data.vo2max), 0,
                                  f"VO2max {num(data.vo2max, 0)}"))  # fmt: skip
        result.warnings.append("Sin marcas recientes: la previsión usa solo el VO2max del reloj (poco fiable).")

    if abs(distance_m - MARATHON_M) < 1000 and data.avg_pace_s_km and data.km_per_week > 0:
        km_week = num(data.km_per_week, 0)
        if data.km_per_week < TANDA_MIN_KM_WEEK:
            # Fuera del rango en que se validó el modelo: sus resultados no tienen sentido.
            result.warnings.append(
                f"Tanda no se aplica con {km_week} km/semana (necesita al menos {TANDA_MIN_KM_WEEK}): "
                "la previsión de maratón usa solo Riegel y VDOT."
            )
        else:
            tanda_s = tanda_marathon_s(data.km_per_week, data.avg_pace_s_km)
            detail = f"{km_week} km/semana a {_clock(data.avg_pace_s_km)} /km"
            models.append(ModelResult("tanda", "Tanda (entrenamiento)", tanda_s, 0, detail))
            if data.km_per_week < 40:
                result.warnings.append(
                    f"Tanda se validó sobre todo con más volumen ({km_week} km/semana): tómalo con cautela."
                )

    weights = model_weights(distance_m, any(m.key == "tanda" for m in models))
    total = sum(weights.get(m.key, 0) for m in models)
    for m in models:
        m.weight = round(weights.get(m.key, 0) / total, 2)
    probable = sum(m.time_s * m.weight for m in models)

    spread_pct = base_uncertainty(distance_m)
    if len(models) > 1:
        times = [m.time_s for m in models]
        spread_pct = max(spread_pct, (max(times) - min(times)) / 2 / probable)
    optimistic_extra = 0.0
    if result.vdot_source == "marca":
        optimistic_extra = TRAINING_MARKS_EXTRA
        result.warnings.append(
            "Tus marcas son tramos de entrenamiento, no carreras: la previsión probablemente sea conservadora."
        )
    if distance_m > MARATHON_M * 1.02:
        spread_pct *= 2
        result.warnings.append("Distancia mayor que maratón: es una extrapolación con un margen muy amplio.")
    elif data.longest_run_m and distance_m > data.longest_run_m * 1.05:
        spread_pct *= 1.5
        result.warnings.append(
            f"Tu tirada más larga reciente es de {num(data.longest_run_m / 1000, 1)} km, menos que la distancia "
            "objetivo: el rango es más amplio."
        )

    if calibration:
        probable *= calibration
        result.calibration_factor = round(calibration, 3)
    result.models = models
    result.spread_pct = round(spread_pct + optimistic_extra / 2, 4)
    result.probable_s = round(probable)
    result.optimistic_s = round(probable * (1 - spread_pct - optimistic_extra))
    result.conservative_s = round(probable * (1 + spread_pct))
    return result


def calibration_factor(results: list[tuple[float, float]]) -> float | None:
    """Mediana de real / previsto en carreras ya disputadas, acotada a ±10 %."""
    ratios = [real / predicted for real, predicted in results if real and predicted]
    if not ratios:
        return None
    return min(max(statistics.median(ratios), CALIBRATION_BOUNDS[0]), CALIBRATION_BOUNDS[1])


def readiness_targets(distance_m: float) -> tuple[float, float]:
    """(tirada larga en km, km/semana) recomendados orientativamente para la distancia."""
    for limit, long_km, weekly_km in READINESS:
        if distance_m <= limit * 1.02:
            return long_km, weekly_km
    return min(distance_m / 1000 * 0.75, 35), 60


def projected_tsb(loads: dict[date, float], today: date, race_day: date, taper_days: int = 10) -> float | None:
    """
    Forma (TSB) prevista el día de la carrera si mantienes tu carga media de 4 semanas
    y la reduces a la mitad los últimos `taper_days` días (afinamiento).
    """
    if not loads or race_day <= today:
        return None
    recent = [loads.get(today - timedelta(days=i), 0.0) for i in range(28)]
    average = statistics.fmean(recent)
    future = dict(loads)
    day = today + timedelta(days=1)
    while day <= race_day:
        future[day] = average * (0.5 if (race_day - day).days < taper_days else 1.0)
        day += timedelta(days=1)
    series = prog.fitness_series(future, race_day, race_day)
    return series[-1]["tsb"] if series else None


def checklist(distance_m: float, data: TrainingData, tsb_race: float | None, weeks_left: float,
              vdot_needed: float | None, vdot_current: float | None) -> list[dict]:  # fmt: skip
    long_km, weekly_km = readiness_targets(distance_m)
    items = [
        {
            "key": "long_run",
            "label": f"Tirada larga de al menos {long_km:g} km (últimas 12 semanas)",
            "status": "ok" if data.longest_run_m / 1000 >= long_km else "pending",
            "current": f"{num(data.longest_run_m / 1000, 1)} km",
        },
        {
            "key": "weekly_volume",
            "label": f"Media de {weekly_km:g} km/semana (últimas 8 semanas)",
            "status": "ok" if data.km_per_week >= weekly_km else "pending",
            "current": f"{num(data.km_per_week, 1)} km/semana",
        },
    ]
    if tsb_race is not None:
        tsb_race = round(tsb_race)  # se evalúa el mismo valor que se muestra
        items.append(
            {
                "key": "taper",
                "label": "Llegar fresco: frescura (TSB) entre +5 y +25 el día de la carrera",
                "status": "ok" if 5 <= tsb_race <= 25 else "warn",
                "current": f"{num(tsb_race, 0, sign=True)} previsto con 10 días de afinamiento",
            }
        )
    if vdot_needed and vdot_current:
        gap = vdot_needed - vdot_current
        items.append(
            {
                "key": "vdot_gap",
                "label": "Objetivo alcanzable con tu forma actual",
                "status": "ok"
                if gap <= 0
                else "pending"
                if gap <= max(1.0, weeks_left * VDOT_GAIN_PER_WEEK)
                else "warn",
                "current": f"VDOT necesario {num(vdot_needed, 1)} · actual {num(vdot_current, 1)}",
            }
        )
    return items


def _clock(seconds: float) -> str:
    s = round(seconds)
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


# ─── Datos del usuario ───────────────────────────────────────────────────────


def training_data(activities: list[Activity], as_of: date) -> TrainingData:
    """Datos de entrenamiento hasta `as_of` (incluido): mejores marcas de 12 meses, volumen de 8 semanas…"""
    runs = [a for a in activities if sport_family(a.sport) == "running"]
    dated = [(a, local_day(a.start_time, a.timezone)) for a in runs]
    efforts: dict[str, tuple[float, float, date]] = {}
    for a, day in dated:
        if not (as_of - timedelta(days=365) < day <= as_of):
            continue
        for key, distance in RECORD_DISTANCES.items():
            time_s = a.metrics.get(key)
            if time_s and (key not in efforts or time_s < efforts[key][1]):
                efforts[key] = (float(distance), float(time_s), day)

    eight = [a for a, day in dated if as_of - timedelta(weeks=8) < day <= as_of]
    km = sum((a.distance_m or 0) for a in eight) / 1000
    seconds = sum(a.moving_duration_s or a.duration_s for a in eight)
    longest = max((a.distance_m or 0 for a, day in dated if as_of - timedelta(weeks=12) < day <= as_of), default=0)
    vo2 = next((a.metrics["vo2max"] for a, day in reversed(dated) if day <= as_of and a.metrics.get("vo2max")), None)
    return TrainingData(
        efforts=efforts,
        vo2max=vo2,
        km_per_week=km / 8,
        avg_pace_s_km=seconds / km if km else None,
        longest_run_m=longest,
    )


def user_calibration(session: Session, user_id: int, exclude_goal: int | None = None) -> float | None:
    rows = session.exec(
        select(RaceGoal).where(RaceGoal.user_id == user_id, col(RaceGoal.result_time_s).is_not(None))
    ).all()
    return calibration_factor([(g.result_time_s, g.predicted_time_s) for g in rows if g.id != exclude_goal])


def goal_forecast(session: Session, goal: RaceGoal, as_of: date | None = None, calibrate: bool = True) -> Forecast:
    as_of = min(as_of or date.today(), goal.race_date)
    activities = prog.user_activities(session, goal.user_id)
    calibration = user_calibration(session, goal.user_id, exclude_goal=goal.id) if calibrate else None
    return forecast(goal.distance_m, training_data(activities, as_of), calibration)


def evolution(session: Session, goal: RaceGoal, weeks: int = 16) -> list[dict]:
    """Previsión semana a semana (cada domingo) hasta hoy o la fecha de la carrera."""
    end = min(date.today(), goal.race_date)
    activities = prog.user_activities(session, goal.user_id)
    calibration = user_calibration(session, goal.user_id, exclude_goal=goal.id)
    points = []
    sunday = end - timedelta(days=(end.weekday() + 1) % 7)
    for i in range(weeks - 1, -1, -1):
        day = sunday - timedelta(weeks=i)
        f = forecast(goal.distance_m, training_data(activities, day), calibration)
        if f.probable_s:
            points.append({"day": day, "probable_s": f.probable_s, "optimistic_s": f.optimistic_s,
                           "conservative_s": f.conservative_s})  # fmt: skip
    return points


def _goal_age_grade(session: Session, goal: RaceGoal, f: Forecast) -> dict | None:
    """% de ajuste por edad de la previsión y del objetivo (edad el día de la carrera)."""
    profile = get_profile(session, goal.user_id)
    if not (profile.birth_date and profile.sex):
        return None
    age = age_on(profile.birth_date, goal.race_date)
    return {
        "age": age,
        "probable": age_grade(goal.distance_m, f.probable_s, age, profile.sex) if f.probable_s else None,
        "target": age_grade(goal.distance_m, goal.target_time_s, age, profile.sex) if goal.target_time_s else None,
    }


def full_report(session: Session, goal: RaceGoal) -> dict:
    today = date.today()
    activities = prog.user_activities(session, goal.user_id)
    data = training_data(activities, min(today, goal.race_date))
    f = goal_forecast(session, goal)
    vdot_needed = vdot(goal.distance_m, goal.target_time_s) if goal.target_time_s else None
    thresholds = prog.user_thresholds(session, goal.user_id)
    per_day, _ = prog.loads_by_day(activities, thresholds, prog.user_rpes(session, goal.user_id))
    weeks_left = max((goal.race_date - today).days / 7, 0)
    evo = evolution(session, goal)
    data_then = training_data(activities, evo[0]["day"]) if evo else None
    # Import local: forecast_explain depende de este módulo.
    from app.services.forecast_explain import explain_forecast

    explanation = explain_forecast(f, data, goal.distance_m, goal.target_time_s, vdot_needed, weeks_left, evo,
                                   data_then)  # fmt: skip
    return {
        "forecast": f,
        "gap_s": round(f.probable_s - goal.target_time_s) if f.probable_s and goal.target_time_s else None,
        "vdot_needed": round(vdot_needed, 1) if vdot_needed else None,
        "weeks_left": round(weeks_left, 1),
        "evolution": evo,
        "explanation": explanation,
        "checklist": checklist(
            goal.distance_m,
            data,
            projected_tsb(per_day, today, goal.race_date),
            weeks_left,
            vdot_needed,
            f.vdot_current,
        ),  # fmt: skip
        "paces": daniels_paces(f.vdot_current) if f.vdot_current else None,
        "age_grade": _goal_age_grade(session, goal, f),
    }
