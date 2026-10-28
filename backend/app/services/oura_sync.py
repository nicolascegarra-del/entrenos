"""
Datos del anillo Oura → modelos de la app.

- Resúmenes diarios (sueño, preparación, actividad, SpO2, estrés, resiliencia, VO2max, edad cardiovascular,
  hora óptima de dormir): se guardan tal cual en `DailyMetric.raw["oura"][tipo]` (sin las series pesadas) y
  se traducen a métricas del catálogo con `day_metrics` (función pura) → `daily_sources` las combina con el reloj.
- Series (FC continua, hipnograma, movimiento, FC/HRV nocturnas, clase de actividad cada 5 min, MET):
  `DailySeries` con fuente `oura`.
- Sesiones (meditación, respiración…), etiquetas, modo descanso, anillo (configuración y batería).
- Entrenos → `save_imported(..., "oura", id)`: si ya existe el mismo entreno de otro reloj, no se duplica.

Sueño: el periodo `long_sleep` más largo (o, si no hay, el más largo) da las métricas de la noche; los demás
periodos válidos son siestas (`naps_s` y en el raw). Los `deleted` y `rest` (descartados) no cuentan.
"""

import contextlib
import logging
import re
import statistics
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlmodel import Session, col, delete, select

from app.models import (
    Activity,
    DailyMetric,
    DailySeries,
    HealthTag,
    OuraConnection,
    RestPeriod,
    User,
    WellnessSession,
)
from app.services import daily_sources
from app.services.file_import import ImportedActivity, after_import, save_imported, sport_name
from app.services.oura_client import OuraAuthError, OuraClient, OuraError, OuraScopeError

logger = logging.getLogger(__name__)

SOURCE = "oura"
# Tipo de dato (nombre de los webhooks) → colección de la API (solo cambia VO2max).
COLLECTIONS = {"vo2_max": "vO2_max"}
DAILY_TYPES = (
    "daily_sleep", "daily_readiness", "daily_activity", "daily_spo2", "daily_stress", "daily_resilience",
    "daily_cardiovascular_age", "vo2_max", "sleep_time",
)  # fmt: skip
RANGE_TYPES = ("sleep", *DAILY_TYPES, "session", "tag", "enhanced_tag", "rest_mode_period", "workout")
WEBHOOK_TYPES = (
    "tag", "enhanced_tag", "workout", "session", "sleep", "daily_sleep", "daily_readiness", "daily_activity",
    "daily_spo2", "sleep_time", "rest_mode_period", "ring_configuration", "daily_stress",
    "daily_cardiovascular_age", "daily_resilience", "vo2_max",
)  # fmt: skip
HEAVY_SLEEP_KEYS = ("heart_rate", "hrv", "movement_30_sec", "sleep_phase_30_sec", "sleep_phase_5_min",
                    "app_sleep_phase_5_min")  # fmt: skip
HEAVY_ACTIVITY_KEYS = ("met", "class_5_min")
SLEEP_SERIES = ("hypnogram_5min", "hypnogram_30s", "movement_30s", "sleep_hr", "sleep_hrv")
RESILIENCE_LEVELS = {"limited": 1, "adequate": 2, "solid": 3, "strong": 4, "exceptional": 5}
HEARTRATE_CHUNK_DAYS = 7
LOW_BATTERY = 15
DELETE_LOOKBACK_DAYS = 400

SPORTS = {
    "walking": "walking", "running": "running", "cycling": "cycling", "hiking": "hiking",
    "swimming": "lap_swimming", "strength_training": "strength_training", "weight_lifting": "strength_training",
    "yoga": "yoga", "pilates": "pilates", "indoor_cycling": "indoor_cycling", "treadmill": "treadmill_running",
    "mountain_biking": "mountain_biking", "elliptical": "elliptical", "rowing": "rowing",
}  # fmt: skip
SPORT_LABELS = {"walking": "Caminata", "running": "Carrera", "cycling": "Ciclismo", "hiking": "Senderismo",
                "lap_swimming": "Natación", "strength_training": "Fuerza", "yoga": "Yoga"}  # fmt: skip
TAG_LABELS = {
    "alcohol": "Alcohol", "caffeine": "Cafeína", "sick": "Enfermedad", "sickness": "Enfermedad",
    "late_meal": "Cena tarde", "travel": "Viaje", "stress": "Estrés", "sauna": "Sauna", "nap": "Siesta",
    "meditation": "Meditación", "headache": "Dolor de cabeza", "period": "Menstruación", "jet_lag": "Jet lag",
    "workout": "Entreno", "medication": "Medicación", "injury": "Lesión", "vacation": "Vacaciones",
}  # fmt: skip


def oura_enabled(session: Session, user: User | int | None) -> bool:
    """
    ¿Puede esta cuenta usar Oura? ÚNICO punto que consulta el módulo `oura` (activado por defecto):
    la API, las vistas de salud, los webhooks y las tareas pasan por aquí.
    """
    from app.services import modules

    return modules.enabled(session, "oura", user)


# ─── Utilidades puras ────────────────────────────────────────────────────────


def collection(data_type: str) -> str:
    return COLLECTIONS.get(data_type, data_type)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def parse_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _mean(items: Any) -> float | None:
    values = [float(v) for v in items or [] if _num(v) is not None]
    return round(statistics.fmean(values), 1) if values else None


def strip(doc: dict, keys: tuple[str, ...]) -> dict:
    return {k: v for k, v in doc.items() if k not in keys}


def main_and_naps(periods: list[dict]) -> tuple[dict | None, list[dict]]:
    """Periodo principal de la noche (`long_sleep` más largo, o el más largo) y siestas."""
    valid = [p for p in periods if p.get("type") not in ("deleted", "rest")]
    if not valid:
        return None, []
    longs = [p for p in valid if p.get("type") == "long_sleep"]
    main = max(longs or valid, key=lambda p: _num(p.get("total_sleep_duration")) or 0)
    return main, [p for p in valid if p is not main]


def _contributors(prefix: str, doc: dict | None) -> dict[str, float]:
    items = (doc or {}).get("contributors") or {}
    return {f"oura_{prefix}_{k}": v for k, raw in items.items() if (v := _num(raw)) is not None}


def sleep_metrics(main: dict | None, naps: list[dict]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    if main:
        out |= {
            "sleep_seconds": _num(main.get("total_sleep_duration")),
            "sleep_deep_s": _num(main.get("deep_sleep_duration")),
            "sleep_rem_s": _num(main.get("rem_sleep_duration")),
            "sleep_light_s": _num(main.get("light_sleep_duration")),
            "sleep_awake_s": _num(main.get("awake_time")),
            "sleep_latency_s": _num(main.get("latency")),
            "sleep_efficiency": _num(main.get("efficiency")),
            "time_in_bed_s": _num(main.get("time_in_bed")),
            "restless_periods": _num(main.get("restless_periods")),
            "breath_rate": _num(main.get("average_breath")),
            "avg_hr_sleep": _num(main.get("average_heart_rate")),
            "resting_hr": _num(main.get("lowest_heart_rate")),
            "hrv_last_night": _num(main.get("average_hrv")),
        }
    if naps:
        out["naps_s"] = sum(_num(p.get("total_sleep_duration")) or 0 for p in naps)
    return out


def day_metrics(oura: dict) -> dict[str, float]:
    """
    Métricas del catálogo de un día a partir de los documentos de Oura guardados (`raw["oura"]`).

    Función pura: misma entrada, misma salida (sirve para recalcular cuando llega un tipo nuevo).
    """
    out: dict[str, float | None] = {}
    main, naps = main_and_naps(oura.get("sleep") or [])
    out |= sleep_metrics(main, naps)
    if d := oura.get("daily_sleep"):
        out["sleep_score"] = _num(d.get("score"))
        out |= _contributors("sleep", d)
    if d := oura.get("daily_readiness"):
        out |= {
            "readiness_score": _num(d.get("score")),
            "temperature_deviation": _num(d.get("temperature_deviation")),
            "temperature_trend_deviation": _num(d.get("temperature_trend_deviation")),
        }
        out |= _contributors("readiness", d)
    if d := oura.get("daily_activity"):
        out |= {
            "activity_score": _num(d.get("score")),
            "steps_daily": _num(d.get("steps")),
            "active_calories": _num(d.get("active_calories")),
            "total_calories": _num(d.get("total_calories")),
            "high_activity_time_s": _num(d.get("high_activity_time")),
            "medium_activity_time_s": _num(d.get("medium_activity_time")),
            "low_activity_time_s": _num(d.get("low_activity_time")),
            "sedentary_time_s": _num(d.get("sedentary_time")),
            "high_activity_met_min": _num(d.get("high_activity_met_minutes")),
            "medium_activity_met_min": _num(d.get("medium_activity_met_minutes")),
            "low_activity_met_min": _num(d.get("low_activity_met_minutes")),
            "sedentary_met_min": _num(d.get("sedentary_met_minutes")),
            "non_wear_s": _num(d.get("non_wear_time")),
            "inactivity_alerts": _num(d.get("inactivity_alerts")),
            "equivalent_walking_distance": _num(d.get("equivalent_walking_distance")),
        }
        out |= _contributors("activity", d)
    if d := oura.get("daily_spo2"):
        out["spo2_avg"] = _num((d.get("spo2_percentage") or {}).get("average"))
        out["breathing_disturbance_index"] = _num(d.get("breathing_disturbance_index"))
    if d := oura.get("daily_stress"):
        out["stress_high_s"] = _num(d.get("stress_high"))
        out["recovery_high_s"] = _num(d.get("recovery_high"))
    if d := oura.get("daily_resilience"):
        level = RESILIENCE_LEVELS.get(str(d.get("level") or ""))
        out["resilience_level"] = float(level) if level else None
        out |= _contributors("resilience", d)
    if d := oura.get("vo2_max"):
        out["vo2max_oura"] = _num(d.get("vo2_max"))
    if d := oura.get("daily_cardiovascular_age"):
        out["cardio_age"] = _num(d.get("vascular_age"))
        out["pulse_wave_velocity"] = _num(d.get("pulse_wave_velocity"))
    return {k: v for k, v in out.items() if v is not None}


def sleep_series(period: dict) -> dict[str, dict]:
    """Series del periodo principal: hipnogramas, movimiento, FC y HRV nocturnas."""
    start = period.get("bedtime_start")
    out: dict[str, dict] = {}
    if period.get("sleep_phase_5_min"):
        out["hypnogram_5min"] = {"start": start, "phases": str(period["sleep_phase_5_min"])}
    if period.get("sleep_phase_30_sec"):
        out["hypnogram_30s"] = {"start": start, "phases": str(period["sleep_phase_30_sec"])}
    if period.get("movement_30_sec"):
        out["movement_30s"] = {"start": start, "values": str(period["movement_30_sec"])}
    for kind, key in (("sleep_hr", "heart_rate"), ("sleep_hrv", "hrv")):
        sample = period.get(key) or {}
        if sample.get("items"):
            out[kind] = {"start": sample.get("timestamp") or start, "interval": sample.get("interval"),
                         "items": sample["items"]}  # fmt: skip
    return out


def activity_series(doc: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if doc.get("class_5_min"):
        out["activity_class_5min"] = {"start": doc.get("timestamp"), "classes": str(doc["class_5_min"])}
    met = doc.get("met") or {}
    if met.get("items"):
        out["met"] = {"start": met.get("timestamp") or doc.get("timestamp"), "interval": met.get("interval"),
                      "items": met["items"]}  # fmt: skip
    return out


def tag_label(code: str | None) -> str:
    key = (code or "").removeprefix("tag_generic_").removeprefix("tag_")
    return TAG_LABELS.get(key) or key.replace("_", " ").capitalize() or "Etiqueta"


def workout_sport(activity: str | None) -> str:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", activity or "").lower().replace(" ", "_")
    return SPORTS.get(snake) or sport_name(snake)


# ─── Guardado ────────────────────────────────────────────────────────────────


def _put_series(session: Session, user_id: int, day: date, kind: str, data: dict) -> None:
    row = session.exec(select(DailySeries).where(
        DailySeries.user_id == user_id, DailySeries.day == day, DailySeries.source == SOURCE, DailySeries.kind == kind
    )).first() or DailySeries(user_id=user_id, day=day, source=SOURCE, kind=kind)  # fmt: skip
    row.data = data
    session.add(row)


def _drop_series(session: Session, user_id: int, day: date, kinds: tuple[str, ...]) -> None:
    session.exec(delete(DailySeries).where(
        DailySeries.user_id == user_id, DailySeries.day == day, DailySeries.source == SOURCE,
        col(DailySeries.kind).in_(kinds),
    ))  # fmt: skip


def _daily_row(session: Session, user_id: int, day: date) -> DailyMetric | None:
    return session.exec(select(DailyMetric).where(DailyMetric.user_id == user_id, DailyMetric.day == day)).first()


def _save_day(session: Session, user_id: int, day: date, oura: dict, prefs: daily_sources.Prefs) -> None:
    daily_sources.set_source_metrics(session, user_id, day, SOURCE, day_metrics(oura), raw=oura, prefs=prefs)


def store_daily(session: Session, user_id: int, data_type: str, docs: list[dict], prefs: daily_sources.Prefs) -> int:
    """Resúmenes diarios (`daily_*`, `vo2_max`, `sleep_time`): uno por día."""
    count = 0
    for doc in docs:
        day = parse_day(doc.get("day"))
        if day is None:
            continue
        row = _daily_row(session, user_id, day)
        oura = dict(((row.raw or {}) if row else {}).get(SOURCE) or {})
        if data_type == "daily_activity":
            for kind, data in activity_series(doc).items():
                _put_series(session, user_id, day, kind, data)
            doc = strip(doc, HEAVY_ACTIVITY_KEYS)
        oura[data_type] = doc
        _save_day(session, user_id, day, oura, prefs)
        count += 1
    return count


def store_sleep(session: Session, user_id: int, docs: list[dict], prefs: daily_sources.Prefs,
                replace_days: bool = True) -> int:  # fmt: skip
    """
    Periodos de sueño. Con `replace_days` (sincronización por fechas) los de cada día sustituyen a los
    guardados; sin él (webhook de un periodo) se añaden o actualizan por id.
    """
    by_day: dict[date, list[dict]] = defaultdict(list)
    for doc in docs:
        if (day := parse_day(doc.get("day"))) is not None:
            by_day[day].append(doc)
    for day, periods in by_day.items():
        row = _daily_row(session, user_id, day)
        oura = dict(((row.raw or {}) if row else {}).get(SOURCE) or {})
        stored = [] if replace_days else list(oura.get("sleep") or [])
        ids = {p.get("id") for p in periods}
        merged = [p for p in stored if p.get("id") not in ids] + [strip(p, HEAVY_SLEEP_KEYS) for p in periods]
        main, _ = main_and_naps(periods)
        if main is not None:
            merged_main = main_and_naps(merged)[0]
            if merged_main is not None and merged_main.get("id") == main.get("id"):
                _drop_series(session, user_id, day, SLEEP_SERIES)
                for kind, data in sleep_series(main).items():
                    _put_series(session, user_id, day, kind, data)
        oura["sleep"] = merged
        _save_day(session, user_id, day, oura, prefs)
    return sum(len(p) for p in by_day.values())


def store_heartrate(session: Session, user_id: int, rows: list[dict]) -> int:
    """FC continua por día (UTC): [[epoch_s, bpm, origen]] sin repetir instantes."""
    by_day: dict[date, dict[int, list]] = defaultdict(dict)
    for r in rows:
        t, bpm = parse_time(r.get("timestamp")), _num(r.get("bpm"))
        if t is None or bpm is None:
            continue
        t = t.astimezone(UTC)
        epoch = int(t.timestamp())
        by_day[t.date()][epoch] = [epoch, round(bpm), str(r.get("source") or "")]
    for day, points in by_day.items():
        row = session.exec(select(DailySeries).where(
            DailySeries.user_id == user_id, DailySeries.day == day, DailySeries.source == SOURCE,
            DailySeries.kind == "heartrate",
        )).first()  # fmt: skip
        existing = {int(p[0]): p for p in ((row.data or {}).get("points") or [])} if row else {}
        existing.update(points)
        _put_series(session, user_id, day, "heartrate", {"points": [existing[k] for k in sorted(existing)]})
    return sum(len(p) for p in by_day.values())


def store_sessions(session: Session, user_id: int, docs: list[dict]) -> int:
    for doc in docs:
        start = parse_time(doc.get("start_datetime"))
        if not doc.get("id") or start is None:
            continue
        ext = str(doc["id"])
        row = session.exec(select(WellnessSession).where(
            WellnessSession.user_id == user_id, WellnessSession.source == SOURCE, WellnessSession.external_id == ext,
        )).first() or WellnessSession(user_id=user_id, source=SOURCE, external_id=ext, start=start)  # fmt: skip
        row.type = str(doc.get("type") or "")[:32]
        row.start, row.end = start, parse_time(doc.get("end_datetime"))
        row.mood = str(doc["mood"])[:16] if doc.get("mood") else None
        row.hr_avg = _mean((doc.get("heart_rate") or {}).get("items"))
        row.hrv_avg = _mean((doc.get("heart_rate_variability") or {}).get("items"))
        row.raw = doc
        session.add(row)
    return len(docs)


def store_tags(session: Session, user_id: int, data_type: str, docs: list[dict]) -> int:
    count = 0
    for doc in docs:
        if not doc.get("id"):
            continue
        if data_type == "enhanced_tag":
            start, end = parse_time(doc.get("start_time")), parse_time(doc.get("end_time"))
            day = parse_day(doc.get("start_day")) or (start.date() if start else None)
            label = doc.get("custom_name") or tag_label(doc.get("tag_type_code"))
            comment = doc.get("comment") or ""
        else:
            start, end = parse_time(doc.get("timestamp")), None
            day = parse_day(doc.get("day")) or (start.date() if start else None)
            label = ", ".join(tag_label(t) for t in doc.get("tags") or []) or (doc.get("text") or "Etiqueta")
            comment = doc.get("text") or ""
        if day is None:
            continue
        row = session.exec(select(HealthTag).where(
            HealthTag.user_id == user_id, HealthTag.source == SOURCE, HealthTag.external_id == str(doc["id"])
        )).first() or HealthTag(user_id=user_id, source=SOURCE, external_id=str(doc["id"]), day=day)  # fmt: skip
        row.day, row.start, row.end = day, start, end
        row.label, row.comment, row.raw = str(label)[:120], str(comment)[:500], doc
        session.add(row)
        count += 1
    return count


def store_rest_periods(session: Session, user_id: int, docs: list[dict]) -> int:
    count = 0
    for doc in docs:
        start = parse_day(doc.get("start_day"))
        if not doc.get("id") or start is None:
            continue
        ext = str(doc["id"])
        row = session.exec(select(RestPeriod).where(
            RestPeriod.user_id == user_id, RestPeriod.source == SOURCE, RestPeriod.external_id == ext
        )).first() or RestPeriod(user_id=user_id, source=SOURCE, external_id=ext, start_date=start)  # fmt: skip
        row.start_date, row.end_date, row.raw = start, parse_day(doc.get("end_day")), doc
        session.add(row)
        count += 1
    return count


def store_ring(conn: OuraConnection, configs: list[dict], battery: list[dict]) -> None:
    """Anillo más reciente (configuración) y última batería leída en `conn.ring`."""
    ring = dict(conn.ring or {})
    if configs:
        latest = max(configs, key=lambda c: str(c.get("set_up_at") or ""))
        ring |= {
            "model": latest.get("hardware_type"),
            "color": latest.get("color"),
            "design": latest.get("design"),
            "size": latest.get("size"),
            "firmware": latest.get("firmware_version"),
        }
    rows = [b for b in battery if _num(b.get("level")) is not None]
    if rows:
        last = max(rows, key=lambda b: str(b.get("timestamp") or ""))
        ring |= {"battery_level": int(last["level"]), "battery_at": last.get("timestamp"),
                 "charging": bool(last.get("charging") or last.get("in_charger"))}  # fmt: skip
    conn.ring = ring


def _workout_hr(session: Session, user_id: int, start: datetime, end: datetime) -> tuple[float | None, float | None]:
    """FC media y máxima de la FC continua con origen `workout` dentro del entreno."""
    days = {start.astimezone(UTC).date(), end.astimezone(UTC).date()}
    rows = session.exec(select(DailySeries).where(
        DailySeries.user_id == user_id, DailySeries.source == SOURCE, DailySeries.kind == "heartrate",
        col(DailySeries.day).in_(days),
    )).all()  # fmt: skip
    t0, t1 = start.timestamp(), end.timestamp()
    bpm = [p[1] for r in rows for p in (r.data or {}).get("points") or []
           if len(p) >= 3 and p[2] == "workout" and t0 <= p[0] <= t1]  # fmt: skip
    return (round(statistics.fmean(bpm)), max(bpm)) if bpm else (None, None)


def store_workouts(session: Session, user_id: int, docs: list[dict]) -> int:
    """Entrenos de Oura sin duplicar los del reloj (mismo inicio ±2 min y duración ±5 %)."""
    created = 0
    for doc in docs:
        start, end = parse_time(doc.get("start_datetime")), parse_time(doc.get("end_datetime"))
        if not doc.get("id") or start is None or end is None or end <= start:
            continue
        sport = workout_sport(doc.get("activity"))
        avg_hr, max_hr = _workout_hr(session, user_id, start, end)
        offset = start.utcoffset()
        tz = None
        if offset is not None:
            minutes = int(offset.total_seconds() // 60)
            tz = f"{'+' if minutes >= 0 else '-'}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"
        act = ImportedActivity(
            sport=sport, start_time=start.astimezone(UTC), duration_s=(end - start).total_seconds(),
            distance_m=_num(doc.get("distance")), calories=_num(doc.get("calories")), avg_hr=avg_hr, max_hr=max_hr,
            name=str(doc.get("label") or f"{SPORT_LABELS.get(sport, 'Entreno')} · Oura")[:255], timezone=tz,
        )  # fmt: skip
        activity, new = save_imported(session, user_id, act, SOURCE, str(doc["id"]))
        if new and activity is not None:
            created += 1
    return created


def store(session: Session, user_id: int, data_type: str, docs: list[dict], prefs: daily_sources.Prefs,
          replace_days: bool = True) -> int:  # fmt: skip
    """Guarda documentos de un tipo de dato de Oura (sin commit, salvo los entrenos)."""
    if data_type == "sleep":
        return store_sleep(session, user_id, docs, prefs, replace_days)
    if data_type in DAILY_TYPES:
        return store_daily(session, user_id, data_type, docs, prefs)
    if data_type == "session":
        return store_sessions(session, user_id, docs)
    if data_type in ("tag", "enhanced_tag"):
        return store_tags(session, user_id, data_type, docs)
    if data_type == "rest_mode_period":
        return store_rest_periods(session, user_id, docs)
    if data_type == "workout":
        return store_workouts(session, user_id, docs)
    if data_type == "ring_configuration":
        conn = session.get(OuraConnection, user_id)
        if conn is not None:
            store_ring(conn, docs, [])
            session.add(conn)
        return len(docs)
    return 0


# ─── Sincronización ──────────────────────────────────────────────────────────


def _chunks(start: date, end: date, days: int) -> list[tuple[date, date]]:
    out, cur = [], start
    while cur <= end:
        nxt = min(cur + timedelta(days=days - 1), end)
        out.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return out


def sync_range(session: Session, user: User | int, start: date, end: date) -> dict[str, int]:
    """
    Trae TODOS los tipos de dato de Oura entre dos fechas (incluidas) y los guarda.

    La FC continua va primero (por trozos de 7 días) para poder calcular la FC de los entrenos.
    Un tipo sin permiso (scope) se salta; caducidad del token y caídas de Oura se propagan.

    Returns:
        Documentos guardados por tipo.
    """
    user_id = user if isinstance(user, int) else user.id
    conn = session.get(OuraConnection, user_id)
    if conn is None:
        return {}
    client = OuraClient(session, conn)
    prefs = daily_sources.preferences(session, user_id)
    counts: dict[str, int] = {}
    skipped: list[str] = []

    def fetch(name: str, **params: Any) -> list[dict]:
        try:
            return client.collection(name, **params)
        except OuraScopeError:
            skipped.append(name)
            return []

    def guarded(name: str, save: Callable[[], int]) -> int:
        """
        Guarda un tipo de dato sin que un formato inesperado (otro modelo de anillo, un campo nuevo o que
        falta) tumbe el resto: se deshace solo ese tipo, se anota y se sigue con los demás.
        """
        try:
            result = save()
            session.commit()
            return result
        except (OuraAuthError, OuraError):
            raise
        except Exception:  # noqa: BLE001 - datos con forma inesperada: se salta ese tipo
            session.rollback()
            logger.exception("Oura: no se pudo guardar %s; se sigue con el resto", name)
            failed.append(name)
            return 0

    failed: list[str] = []
    hr_rows: list[dict] = []
    for a, b in _chunks(start, end, HEARTRATE_CHUNK_DAYS):
        hr_rows += fetch("heartrate", start_datetime=f"{a.isoformat()}T00:00:00+00:00",
                         end_datetime=f"{(b + timedelta(days=1)).isoformat()}T00:00:00+00:00")  # fmt: skip
    counts["heartrate"] = guarded("heartrate", lambda: store_heartrate(session, user_id, hr_rows))
    # `end_date` +1: así el último día entra seguro aunque Oura lo trate como exclusivo.
    dates = {"start_date": start.isoformat(), "end_date": (end + timedelta(days=1)).isoformat()}
    for data_type in RANGE_TYPES:
        by_day = data_type in ("sleep", *DAILY_TYPES)
        docs = [d for d in fetch(collection(data_type), **dates) if isinstance(d, dict)]
        if by_day:
            docs = [d for d in docs if start <= (parse_day(d.get("day")) or start) <= end]
        counts[data_type] = guarded(data_type, lambda t=data_type, d=docs: store(session, user_id, t, d, prefs))
    conn = session.get(OuraConnection, user_id) or conn
    ring = fetch("ring_configuration")
    battery = fetch("ring_battery_level", latest="true")
    guarded("ring", lambda: store_ring(conn, ring, battery) or 0)
    conn.last_sync_at = datetime.now(UTC)
    conn.status = "ok"
    notes = []
    if skipped:
        notes.append("Sin permiso para: " + ", ".join(skipped))
    if failed:
        notes.append("Datos con formato inesperado (se reintentará): " + ", ".join(failed))
    conn.last_error = ". ".join(notes)[:255]
    session.add(conn)
    session.commit()
    check_battery(session, conn)
    if counts.get("workout"):
        after_import(session, user_id)
    return counts


def check_battery(session: Session, conn: OuraConnection, today: date | None = None) -> bool:
    """Aviso de batería baja (< 15 %, sin cargar) como mucho una vez al día."""
    ring = conn.ring or {}
    level = ring.get("battery_level")
    if not isinstance(level, int | float) or level >= LOW_BATTERY or ring.get("charging"):
        return False
    from app.services.notifications import notify

    day = (today or date.today()).isoformat()
    try:
        return notify(session, conn.user_id, "sync_error", f"oura-battery:{day}", "Batería del anillo baja",
                      f"A tu anillo Oura le queda un {int(level)} %. Ponlo a cargar.", "/ajustes")  # fmt: skip
    except Exception:  # noqa: BLE001 - el aviso es secundario
        session.rollback()
        return False


def _find_day_with(session: Session, user_id: int, data_type: str, object_id: str) -> DailyMetric | None:
    since = date.today() - timedelta(days=DELETE_LOOKBACK_DAYS)
    rows = session.exec(select(DailyMetric).where(DailyMetric.user_id == user_id, col(DailyMetric.day) >= since)).all()
    for row in rows:
        doc = ((row.raw or {}).get(SOURCE) or {}).get(data_type)
        docs = doc if isinstance(doc, list) else [doc] if isinstance(doc, dict) else []
        if any(d.get("id") == object_id for d in docs):
            return row
    return None


def remove_activities(session: Session, ids: list[int]) -> int:
    """
    Borra entrenos que Oura ya no tiene (sin marcarlos como «borrados por la persona»: esa marca impediría
    que el mismo entreno llegara de otro reloj). Las sesiones del plan que los usaban se vuelven a emparejar.
    """
    from app.models import PlannedSession
    from app.services.plan_service import refresh_match

    if not ids:
        return 0
    plans = session.exec(select(PlannedSession).where(col(PlannedSession.activity_id).in_(ids))).all()
    for planned in plans:
        planned.activity_id = None
        session.add(planned)
    session.flush()
    session.exec(delete(Activity).where(col(Activity.id).in_(ids)))
    session.commit()
    for planned in plans:
        session.refresh(planned)
        try:
            refresh_match(session, planned)
        except Exception:  # noqa: BLE001 - el emparejado es secundario
            session.rollback()
    session.commit()
    return len(ids)


def delete_object(session: Session, user_id: int, data_type: str, object_id: str) -> int:
    """Oura avisa de que algo se borró: se quita lo que vino de él (no los datos de otras fuentes)."""
    removed = 0
    if data_type == "workout":
        ids = session.exec(select(Activity.id).where(
            Activity.user_id == user_id, Activity.source == SOURCE, Activity.external_id == object_id
        )).all()  # fmt: skip
        removed = remove_activities(session, list(ids))
    elif data_type in ("session", "tag", "enhanced_tag", "rest_mode_period"):
        model = {"session": WellnessSession, "rest_mode_period": RestPeriod}.get(data_type, HealthTag)
        result = session.exec(delete(model).where(
            model.user_id == user_id, model.source == SOURCE, model.external_id == object_id
        ))  # fmt: skip
        removed = result.rowcount or 0
    elif data_type == "sleep" or data_type in DAILY_TYPES:
        row = _find_day_with(session, user_id, data_type, object_id)
        if row is not None:
            oura = dict((row.raw or {}).get(SOURCE) or {})
            if data_type == "sleep":
                oura["sleep"] = [p for p in oura.get("sleep") or [] if p.get("id") != object_id]
                _drop_series(session, user_id, row.day, SLEEP_SERIES)
            else:
                oura.pop(data_type, None)
                if data_type == "daily_activity":
                    _drop_series(session, user_id, row.day, ("activity_class_5min", "met"))
            _save_day(session, user_id, row.day, oura, daily_sources.preferences(session, user_id))
            removed = 1
    session.commit()
    return removed


def fetch_object(session: Session, user_id: int, data_type: str, object_id: str, event_type: str = "update") -> int:
    """Webhook: trae (o borra) un documento concreto."""
    if data_type not in WEBHOOK_TYPES:
        return 0
    if event_type == "delete":
        return delete_object(session, user_id, data_type, object_id)
    conn = session.get(OuraConnection, user_id)
    if conn is None:
        return 0
    try:
        doc = OuraClient(session, conn).document(collection(data_type), object_id)
    except OuraScopeError:
        return 0  # tipo sin permiso en esta cuenta o este anillo
    if not isinstance(doc, dict) or not doc:
        return 0
    if data_type == "workout":
        # La FC del entreno sale de la FC continua de ese rato (si aún no está, se trae ahora).
        start, end = parse_time(doc.get("start_datetime")), parse_time(doc.get("end_datetime"))
        if start and end:
            with contextlib.suppress(OuraScopeError):
                store_heartrate(session, user_id, OuraClient(session, conn).collection(
                    "heartrate", start_datetime=start.isoformat(), end_datetime=end.isoformat()))  # fmt: skip
    try:
        count = store(session, user_id, data_type, [doc], daily_sources.preferences(session, user_id),
                      replace_days=False)  # fmt: skip
    except Exception:  # noqa: BLE001 - formato inesperado: se ignora este aviso (el sondeo lo reintenta)
        session.rollback()
        logger.exception("Oura: no se pudo guardar el aviso %s %s", data_type, object_id)
        return 0
    conn.last_sync_at = datetime.now(UTC)
    session.add(conn)
    session.commit()
    if data_type == "workout" and count:
        after_import(session, user_id)
    return count


def purge(session: Session, user_id: int) -> None:
    """Borra todo lo que vino de Oura: series, sesiones, etiquetas, modo descanso, entrenos y métricas diarias."""
    for model in (DailySeries, WellnessSession, HealthTag, RestPeriod):
        session.exec(delete(model).where(model.user_id == user_id, model.source == SOURCE))
    session.commit()
    remove_activities(session, list(session.exec(
        select(Activity.id).where(Activity.user_id == user_id, Activity.source == SOURCE)
    ).all()))  # fmt: skip
    daily_sources.remove_source(session, user_id, SOURCE)
