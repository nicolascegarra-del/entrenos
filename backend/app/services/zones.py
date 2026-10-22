"""
Umbrales y zonas de entrenamiento de carrera, con historial y recálculo automático.

- FC umbral (LTHR): la última que dio Garmin o el 89 % de la FC máx. (`progress.user_thresholds`).
- Ritmo umbral: el que calcula Garmin (umbral de lactato del reloj, del último año) si lo hay; si no,
  el más rápido entre el ritmo T de Daniels del VDOT actual, el 96 % de la velocidad crítica (la CS
  queda algo por encima del umbral de lactato; Jones y Vanhatalo, 2017) y el mejor ritmo sostenido
  60 min en los últimos 120 días (el umbral es, por definición, ~el ritmo de una hora).
- Ritmos de entrenamiento (E/M/T/I/R de Daniels): del VDOT de tus marcas o del VDOT equivalente a tu
  ritmo umbral, el mayor de los dos, para que nunca salgan más lentos que el umbral efectivo.
- Zonas de FC y de ritmo de Friel (5 zonas, porcentajes del umbral).

Cada vez que el umbral cambia de forma apreciable se guarda una fila nueva en `AthleteZones`
(vigente desde hoy): así queda el historial y la app puede avisar «tus zonas han cambiado».
"""

from datetime import date, timedelta

from sqlmodel import Session, col, select

from app.models import AthleteZones, DailyMetric
from app.services import progress as prog
from app.services.pace_curve import best_curve, critical_speed
from app.services.race_forecast import forecast, training_data
from app.services.race_models import daniels_paces

GARMIN_LT_MAX_AGE_D = 365
LT_SPEED_RANGE = (2.0, 7.0)  # m/s razonables (8:20 a 2:23 /km)

SPORT = "running"
CS_TO_THRESHOLD = 0.96
LTHR_CHANGE_BPM = 2  # cambios menores no generan zonas nuevas (ruido)
PACE_CHANGE_S = 3
RECENT_DAYS = 14  # «tus zonas han cambiado» se muestra estas semanas

# Friel: FC en % de la LTHR (límite superior de cada zona) y ritmo en % del ritmo umbral (s/km).
HR_ZONES = (("Z1 Recuperación", 0, 0.85), ("Z2 Aeróbica", 0.85, 0.90), ("Z3 Tempo", 0.90, 0.95),
            ("Z4 Umbral", 0.95, 1.00), ("Z5 VO2max", 1.00, None))  # fmt: skip
PACE_ZONES = (("Z1 Recuperación", 1.29, None), ("Z2 Aeróbica", 1.14, 1.29), ("Z3 Tempo", 1.06, 1.14),
              ("Z4 Umbral", 0.99, 1.06), ("Z5 VO2max", None, 0.99))  # fmt: skip


def hr_zones(lthr: float) -> list[dict]:
    return [
        {"name": name, "min": round(lthr * lo), "max": round(lthr * hi) - 1 if hi else None}
        for name, lo, hi in HR_ZONES
    ]


def pace_zones(threshold_pace: float) -> list[dict]:
    """Rangos de ritmo (s/km): `fast` = límite rápido, `slow` = límite lento (None = sin límite)."""
    return [
        {"name": name, "fast": round(threshold_pace * lo) if lo else None,
         "slow": round(threshold_pace * hi) if hi else None}
        for name, lo, hi in PACE_ZONES
    ]  # fmt: skip


def normalize_lt_speed(value: float | None) -> float | None:
    """Garmin da la velocidad umbral en decenas de m/s (0,308 = 3,08 m/s); se aceptan ambas unidades."""
    if not value:
        return None
    speed = value * 10 if value < 1.5 else value
    return round(speed, 3) if LT_SPEED_RANGE[0] <= speed <= LT_SPEED_RANGE[1] else None


def store_garmin_threshold(session: Session, user_id: int, data: dict | None) -> bool:
    """Guarda el umbral de lactato de Garmin (velocidad y FC) en la métrica diaria de su fecha."""
    entry = (data or {}).get("speed_and_heart_rate") or {}
    speed = normalize_lt_speed(entry.get("speed"))
    if speed is None:
        return False
    try:
        day = date.fromisoformat(str(entry.get("calendarDate"))[:10])
    except ValueError:
        day = date.today()
    row = session.exec(select(DailyMetric).where(DailyMetric.user_id == user_id, DailyMetric.day == day)).first()
    row = row or DailyMetric(user_id=user_id, day=day)
    metrics = {**(row.metrics or {}), "lt_speed": speed}
    if entry.get("heartRate"):
        metrics["lt_hr"] = entry["heartRate"]
    row.metrics = metrics
    session.add(row)
    session.commit()
    return True


def garmin_threshold(session: Session, user_id: int, today: date) -> tuple[float, date] | None:
    """Último ritmo umbral de Garmin (s/km) del último año y su fecha."""
    rows = session.exec(
        select(DailyMetric)
        .where(DailyMetric.user_id == user_id, DailyMetric.day >= today - timedelta(days=GARMIN_LT_MAX_AGE_D))
        .order_by(col(DailyMetric.day).desc())
    ).all()
    row = next((r for r in rows if (r.metrics or {}).get("lt_speed")), None)
    return (round(1000 / row.metrics["lt_speed"]), row.day) if row else None


def estimate_thresholds(session: Session, user_id: int, today: date | None = None) -> dict:
    """Umbrales actuales con su origen (para explicarlo en la interfaz)."""
    today = today or date.today()
    activities = prog.user_activities(session, user_id)
    thr = prog.user_thresholds(session, user_id)
    lthr_source = "garmin" if any(a.metrics.get("lthr") for a in activities) else ("fc_max" if thr.lthr else None)
    # Candidatos a ritmo umbral (s/km); se elige el más rápido: el umbral no puede ser más lento que un
    # ritmo que ya has sostenido 60 min, y el VDOT puede quedarse corto si sale de marcas antiguas.
    candidates: dict[str, float] = {}
    f = forecast(10000, training_data(activities, today))
    if f.vdot_current:
        fast, slow = daniels_paces(f.vdot_current)["threshold"]
        candidates["vdot"] = (fast + slow) / 2
    curve = best_curve(session, activities, today - timedelta(days=120), today)
    cs = critical_speed({d: b.speed for d, b in curve.items()})
    if cs:
        candidates["velocidad_critica"] = 1000 / (cs[0] * CS_TO_THRESHOLD)
    if 3600 in curve:
        candidates["mejor_hora"] = 1000 / curve[3600].speed
    garmin = garmin_threshold(session, user_id, today)
    if garmin:
        candidates["garmin"] = garmin[0]
    # Garmin manda (lo mide el reloj con tu FC y ritmo reales); si no, el más rápido de los estimados.
    fastest = min(candidates, key=candidates.get) if candidates else None
    pace_source = "garmin" if garmin else fastest
    pace = round(candidates[pace_source]) if pace_source else None
    return {
        "lthr": round(thr.lthr) if thr.lthr else None,
        "lthr_source": lthr_source,
        "threshold_pace_s_km": pace,
        "pace_source": pace_source,
        "vdot": f.vdot_current,
        "vdot_source": getattr(f, "vdot_source", None),
        "vdot_from_races": getattr(f, "source_is_race", False),
        "candidates": {k: round(v) for k, v in candidates.items()},
        "garmin_date": garmin[1].isoformat() if garmin else None,
    }


def vdot_for_threshold(pace_s_km: float) -> float | None:
    """VDOT cuyo ritmo T (punto medio de Daniels) es `pace_s_km` (búsqueda binaria; T baja al subir el VDOT)."""
    lo, hi = 15.0, 90.0

    def t_mid(v: float) -> float:
        fast, slow = daniels_paces(v)["threshold"]
        return (fast + slow) / 2

    if not (t_mid(hi) <= pace_s_km <= t_mid(lo)):
        return None
    for _ in range(40):
        mid = (lo + hi) / 2
        if t_mid(mid) > pace_s_km:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 1)


def effective_paces(session: Session, user_id: int, today: date | None = None) -> dict | None:
    """
    Ritmos de entrenamiento coherentes con el umbral: VDOT = el mayor entre el de tus marcas y el
    equivalente a tu ritmo umbral efectivo. Devuelve también de dónde sale cada valor.
    """
    thr = estimate_thresholds(session, user_id, today)
    vdot_marks = thr["vdot"]
    vdot_thr = vdot_for_threshold(thr["threshold_pace_s_km"]) if thr["threshold_pace_s_km"] else None
    if not vdot_marks and not vdot_thr:
        return None
    basis = "umbral" if vdot_thr and (not vdot_marks or vdot_thr > vdot_marks) else "marcas"
    v = vdot_thr if basis == "umbral" else vdot_marks
    return {
        "vdot": round(v, 1),
        "basis": basis,
        "vdot_marks": vdot_marks,
        "vdot_source": thr["vdot_source"],
        "vdot_from_races": thr["vdot_from_races"],
        "vdot_threshold": vdot_thr,
        "threshold_pace_s_km": thr["threshold_pace_s_km"],
        "threshold_source": thr["pace_source"],
        "alternatives": thr["candidates"],
        "paces": daniels_paces(v),
    }


def _changed(old: dict, new: dict) -> bool:
    def diff(key: str, limit: float) -> bool:
        a, b = old.get(key), new.get(key)
        if a is None or b is None:
            return a != b
        return abs(a - b) >= limit

    return diff("lthr", LTHR_CHANGE_BPM) or diff("threshold_pace_s_km", PACE_CHANGE_S)


def refresh_zones(session: Session, user_id: int, today: date | None = None) -> AthleteZones | None:
    """
    Recalcula los umbrales y, si han cambiado lo suficiente, guarda zonas nuevas vigentes desde hoy.

    Returns:
        Las zonas vigentes (nuevas o las de antes), o None si aún no hay datos para calcularlas.
    """
    today = today or date.today()
    current = latest_zones(session, user_id)
    thresholds = estimate_thresholds(session, user_id, today)
    if thresholds["lthr"] is None and thresholds["threshold_pace_s_km"] is None:
        return current
    if current is not None and not _changed(current.thresholds, thresholds):
        # Mismo umbral: no hay zonas nuevas, pero se actualizan las alternativas y fuentes que se muestran.
        kept = {k: current.thresholds.get(k) for k in ("lthr", "threshold_pace_s_km", "pace_source")}
        merged = {**thresholds, **kept}
        if merged != current.thresholds:
            current.thresholds = merged
            session.add(current)
            session.commit()
        return current
    zones = {
        "hr": hr_zones(thresholds["lthr"]) if thresholds["lthr"] else [],
        "pace": pace_zones(thresholds["threshold_pace_s_km"]) if thresholds["threshold_pace_s_km"] else [],
    }
    row = session.exec(
        select(AthleteZones).where(
            AthleteZones.user_id == user_id, AthleteZones.sport == SPORT, AthleteZones.valid_from == today
        )
    ).first() or AthleteZones(user_id=user_id, sport=SPORT, valid_from=today)
    row.thresholds, row.zones = thresholds, zones
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def latest_zones(session: Session, user_id: int) -> AthleteZones | None:
    return session.exec(
        select(AthleteZones)
        .where(AthleteZones.user_id == user_id, AthleteZones.sport == SPORT)
        .order_by(col(AthleteZones.valid_from).desc())
    ).first()


def zones_report(session: Session, user_id: int, today: date | None = None) -> dict:
    """Zonas vigentes, historial y si han cambiado hace poco (para el aviso)."""
    today = today or date.today()
    current = refresh_zones(session, user_id, today)
    history = session.exec(
        select(AthleteZones)
        .where(AthleteZones.user_id == user_id, AthleteZones.sport == SPORT)
        .order_by(col(AthleteZones.valid_from).desc())
        .limit(12)
    ).all()
    previous = history[1] if len(history) > 1 else None
    return {
        "current": _out(current),
        "previous": _out(previous),
        "history": [_out(h) for h in history],
        "changed_recently": bool(current and previous and (today - current.valid_from).days <= RECENT_DAYS),
    }


def _out(row: AthleteZones | None) -> dict | None:
    if row is None:
        return None
    return {"valid_from": row.valid_from.isoformat(), "thresholds": row.thresholds, "zones": row.zones}
