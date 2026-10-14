"""
Perfil del atleta y cálculos que dependen de él (funciones puras + persistencia).

- Edad → FC máxima de Tanaka (208 − 0,7·edad) cuando no hay FC máx. real.
- Edad + sexo → percentil de VO2max (registro FRIEND, Kaminsky 2015, tabla 3, cinta).
- Edad + sexo → marca ajustada por edad (factores de ruta USATF/WMA 2025, A. Jones).
- Peso → calorías de sesiones manuales (ecuación de carrera del ACSM o MET del Compendio 2011).
- Altura → IMC y zancada relativa (informativo).
"""

import contextlib
import json
from bisect import bisect_left
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlmodel import Session, select

from app.models import Sex, UserProfile, WeightLog

# ─── Percentiles de VO2max (FRIEND, Kaminsky et al. 2015, Mayo Clin Proc, tabla 3) ─────────
# mL·kg⁻¹·min⁻¹ en cinta, por década de edad, para los percentiles 5, 10, 25, 50, 75, 90 y 95.
FRIEND_PERCENTILES = (5, 10, 25, 50, 75, 90, 95)
FRIEND_VO2MAX = {
    Sex.MALE: {
        20: (29.0, 32.1, 40.1, 48.0, 55.2, 61.8, 66.3),
        30: (27.2, 30.2, 35.9, 42.4, 49.2, 56.5, 59.8),
        40: (24.2, 26.8, 31.9, 37.8, 45.0, 52.1, 55.6),
        50: (20.9, 22.8, 27.1, 32.6, 39.7, 45.6, 50.7),
        60: (17.4, 19.8, 23.7, 28.2, 34.5, 40.3, 43.0),
        70: (16.3, 17.1, 20.4, 24.4, 30.4, 36.6, 39.7),
    },
    Sex.FEMALE: {
        20: (21.7, 23.9, 30.5, 37.6, 44.7, 51.3, 56.0),
        30: (19.0, 20.9, 25.3, 30.2, 36.1, 41.4, 45.8),
        40: (17.0, 18.8, 22.1, 26.7, 32.4, 38.4, 41.7),
        50: (16.0, 17.3, 19.9, 23.4, 27.6, 32.0, 35.9),
        60: (13.4, 14.6, 17.2, 20.0, 23.8, 27.0, 29.4),
        70: (13.1, 13.6, 15.6, 18.3, 20.8, 23.1, 24.1),
    },
}

AGE_GRADE_FILE = Path(__file__).resolve().parent.parent / "data" / "age_grade_road_2025.json"
AGE_GRADE_DISTANCES = (1609, 5000, 10000, 21097.5, 42195)

# MET del Compendio de Actividades 2011 (Ainsworth et al.) por familia de deporte.
MET_BY_SPORT = {
    "strength_training": (3.5, 6.0),  # entrenamiento con pesas: moderado / vigoroso
    "cycling": (6.8, 10.0),  # ciclismo general moderado / vigoroso
    "lap_swimming": (5.8, 9.8),
    "walking": (3.5, 5.0),
    "hiking": (6.0, 7.8),
    "yoga": (2.5, 4.0),
}
DEFAULT_MET = (5.0, 8.0)


def age_on(birth_date: date, today: date) -> int:
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def tanaka_hr_max(age: int) -> float:
    """FC máxima estimada por edad (Tanaka, Monahan y Seals 2001): 208 − 0,7 × edad."""
    return round(208 - 0.7 * age, 1)


def vo2max_percentile(vo2max: float, age: int, sex: Sex) -> dict:
    """
    Percentil de VO2max para la edad y el sexo según la tabla FRIEND, interpolando
    linealmente entre los percentiles publicados (fuera de 5–95 se informa como límite).
    """
    decade = min(max(age // 10 * 10, 20), 70)
    values = FRIEND_VO2MAX[sex][decade]
    if vo2max <= values[0]:
        percentile = 5.0
        bound = "below"
    elif vo2max >= values[-1]:
        percentile = 95.0
        bound = "above"
    else:
        i = bisect_left(values, vo2max)
        lo_v, hi_v = values[i - 1], values[i]
        lo_p, hi_p = FRIEND_PERCENTILES[i - 1], FRIEND_PERCENTILES[i]
        percentile = lo_p + (vo2max - lo_v) / (hi_v - lo_v) * (hi_p - lo_p)
        bound = None
    return {
        "percentile": round(percentile),
        "bound": bound,
        "age_group": f"{decade}–{decade + 9}",
        "median": values[3],
        "out_of_range_age": not 20 <= age <= 79,
    }


@lru_cache
def _age_grade_tables() -> dict:
    return json.loads(AGE_GRADE_FILE.read_text(encoding="utf-8"))


def age_grade(distance_m: float, time_s: float, age: int, sex: Sex) -> dict | None:
    """
    Marca ajustada por edad: estándar de tu edad / tu tiempo (100 % = récord para tu edad y sexo).
    Solo para distancias de la tabla (milla, 5K, 10K, media y maratón, ±2 %).
    """
    key = next((d for d in AGE_GRADE_DISTANCES if abs(distance_m - d) / d <= 0.02), None)
    if key is None or time_s <= 0:
        return None
    table = _age_grade_tables()["male" if sex == Sex.MALE else "female"]
    column = str(key) if key != 21097.5 else "21097.5"
    factor = table["factors"][str(min(max(age, 5), 100))][column]
    standard = table["open_standard_s"][column] / factor
    percent = standard / time_s * 100
    return {"percent": round(percent, 1), "age_standard_s": round(standard), "factor": factor,
            "level": age_grade_level(percent)}  # fmt: skip


def age_grade_level(percent: float) -> str:
    """Niveles orientativos habituales del ajuste por edad."""
    if percent >= 90:
        return "Clase mundial"
    if percent >= 80:
        return "Nivel nacional"
    if percent >= 70:
        return "Nivel regional"
    if percent >= 60:
        return "Nivel local"
    return "Corredor popular"


def calories(sport: str, duration_s: float, weight_kg: float, distance_m: float | None = None,
             rpe: int | None = None) -> float:  # fmt: skip
    """
    Calorías estimadas. Carrera con distancia: ecuación del ACSM (VO₂ = 0,2·v + 3,5 ml/kg/min,
    5 kcal por litro de O₂). Resto: MET del Compendio × kg × horas (vigoroso si RPE ≥ 7).
    """
    hours = duration_s / 3600
    if sport in ("running", "trail_running", "treadmill_running") and distance_m and duration_s:
        speed = distance_m / (duration_s / 60)  # m/min
        vo2 = 0.2 * speed + 3.5
        return round(vo2 * weight_kg / 1000 * 5 * (duration_s / 60))
    moderate, vigorous = MET_BY_SPORT.get(sport, DEFAULT_MET)
    met = vigorous if rpe and rpe >= 7 else moderate
    return round(met * weight_kg * hours)


def bmi(weight_kg: float, height_cm: float) -> float:
    return round(weight_kg / (height_cm / 100) ** 2, 1)


# ─── Persistencia ────────────────────────────────────────────────────────────


def get_profile(session: Session, user_id: int) -> UserProfile:
    return session.get(UserProfile, user_id) or UserProfile(user_id=user_id)


def record_weight(session: Session, user_id: int, weight_kg: float, source: str, day: date | None = None) -> None:
    day = day or date.today()
    entry = session.exec(select(WeightLog).where(WeightLog.user_id == user_id, WeightLog.day == day)).first()
    entry = entry or WeightLog(user_id=user_id, day=day, weight_kg=weight_kg)
    entry.weight_kg, entry.source = weight_kg, source
    session.add(entry)


def profile_from_garmin(garmin_profile: dict) -> dict:
    """Traduce `get_user_profile` de Garmin (peso en gramos, altura en cm) a campos del perfil."""
    data = garmin_profile.get("userData") or {}
    out: dict = {}
    if data.get("birthDate"):
        with contextlib.suppress(ValueError):  # fecha mal formada: se deja vacía
            out["birth_date"] = date.fromisoformat(str(data["birthDate"])[:10])
    gender = str(data.get("gender") or "").lower()
    if gender in ("male", "female"):
        out["sex"] = Sex(gender)
    if data.get("weight"):
        out["weight_kg"] = round(float(data["weight"]) / 1000, 1)
    if data.get("height"):
        out["height_cm"] = round(float(data["height"]), 1)
    return out


def apply_garmin_profile(session: Session, user_id: int, garmin_profile: dict) -> UserProfile:
    """
    Rellena el perfil con los datos de Garmin. Si lo has editado a mano, solo completa los
    campos vacíos para no pisar tus cambios.
    """
    profile = get_profile(session, user_id)
    edited = profile.source == "manual" and any(
        getattr(profile, f) is not None for f in ("birth_date", "sex", "weight_kg", "height_cm")
    )
    for field, value in profile_from_garmin(garmin_profile).items():
        if not edited or getattr(profile, field) is None:
            setattr(profile, field, value)
    if not edited:
        profile.source = "garmin"
    if profile.weight_kg:
        record_weight(session, user_id, profile.weight_kg, "garmin")
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile
