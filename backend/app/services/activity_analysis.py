"""
Análisis de una actividad para su página: tiempo en zonas de FC, VO2max, parciales por km y deriva cardiaca.

- **Zonas de FC**: las de la app (`zones`, las mismas que usa todo el análisis) o, en bici, las del último
  test de umbral de bici si lo hay. Se cuenta el tiempo de cada muestra de pulso (huecos > 30 s fuera).
- **VO2max**: el que calculó el reloj en la actividad (Garmin lo da en carrera y bici). Si no lo trae, en
  carrera se estima: VO2 del ritmo medio (ACSM: 0,2 × m/min + 3,5) dividido entre la fracción de reserva
  de FC usada (Swain: %FCR ≈ %VO2R). Es orientativo: solo con esfuerzo sostenido (50-95 % de la FCR),
  terreno llano (< 15 m de desnivel por km) y al menos 15 min.
- **Parciales por km** (deportes a pie): tiempo, ritmo, FC media y desnivel positivo de cada km.
- **Deriva cardiaca** (Pa:HR): eficiencia (velocidad / FC) de la segunda mitad frente a la primera; por
  encima del 5 % suele indicar falta de base aeróbica, calor o deshidratación (Friel).
- **Pulso de la sesión** (cualquier actividad con serie de FC, también las del anillo Oura): FC mín./media/
  máx., % de la FC máx., deriva de la FC (2.ª mitad frente a la 1.ª, la útil sin distancia) y TRIMP de
  Banister (minutos × reserva de FC × 0,64·e^(1,92·reserva); en mujeres 0,86·e^(1,67·reserva)).
"""

import math

from sqlmodel import Session, select

from app.models import Activity, ActivityStream, DailyMetric, Sex, UserProfile
from app.services import progress as prog
from app.services import run_metrics
from app.services.zones import hr_zones, latest_zones

MAX_GAP_S = 30
MIN_VO2_SECONDS = 900
FLAT_GAIN_PER_KM = 15
MIN_DECOUPLING_S = 1800
MIN_DRIFT_S = 1200
# Vo2max actual: el del reloj (Garmin) y, si no hay, el del anillo Oura.
VO2MAX_DAILY = (("vo2max_running", "reloj"), ("vo2max_oura", "oura"))


def load_streams(session: Session, activity_id: int, channels: tuple[str, ...]) -> dict[str, list]:
    rows = session.exec(
        select(ActivityStream).where(
            ActivityStream.activity_id == activity_id,
            ActivityStream.channel.in_(channels),  # type: ignore[attr-defined]
        )
    ).all()
    return {r.channel: r.values for r in rows}


def zones_for(session: Session, user_id: int, sport: str) -> tuple[list[dict], float | None, str]:
    from app.services.plan_steps import sport_family
    from app.services.test_results import active_test

    if sport_family(sport) == "cycling" and (test := active_test(session, user_id, "cycling", "lthr")):
        lthr = test.results["lthr"]
        return hr_zones(lthr), lthr, "test de bici"
    current = latest_zones(session, user_id)
    if current and current.zones.get("hr"):
        return current.zones["hr"], current.thresholds.get("lthr"), "tus zonas"
    lthr = prog.user_thresholds(session, user_id).lthr
    return (hr_zones(lthr), lthr, "estimadas") if lthr else ([], None, "")


def time_in_zones(time: list, hr: list, zones: list[dict]) -> list[dict]:
    """Segundos y % del tiempo con pulso en cada zona."""
    secs = [0.0] * len(zones)
    for i in range(1, min(len(time), len(hr))):
        h, t0, t1 = hr[i], time[i - 1], time[i]
        if not h or t0 is None or t1 is None or t1 <= t0 or t1 - t0 > MAX_GAP_S:
            continue
        idx = next((k for k, z in enumerate(zones) if z["max"] is None or h <= z["max"]), len(zones) - 1)
        secs[idx] += t1 - t0
    total = sum(secs) or 1
    return [
        {"name": z["name"], "min": z["min"], "max": z["max"], "seconds": round(s), "pct": round(s / total * 100, 1)}
        for z, s in zip(zones, secs, strict=True)
    ]


def splits(time: list, dist: list, hr: list, alt: list, cad: list | None = None) -> list[dict]:
    """
    Parciales por km (el último, si tiene al menos 200 m): ritmo, tiempo acumulado desde la salida,
    FC y cadencia medias (pasos/min, sin contar los ceros de las paradas) y desnivel positivo.
    """
    cad = cad or []
    out: list[dict] = []
    pts = [(t, d, hr[i] if i < len(hr) else None, alt[i] if i < len(alt) else None,
            cad[i] if i < len(cad) else None)
           for i, (t, d) in enumerate(zip(time, dist, strict=False)) if t is not None and d is not None]  # fmt: skip
    if len(pts) < 2:
        return out
    start_i, km = 0, 1
    for i in range(1, len(pts)):
        last = i == len(pts) - 1
        if pts[i][1] >= km * 1000 or last:
            seg = pts[start_i : i + 1]
            meters = seg[-1][1] - seg[0][1]
            seconds = seg[-1][0] - seg[0][0]
            if meters < (1000 if not last else 200) * 0.98 or seconds <= 0:
                break
            hrs = [p[2] for p in seg if p[2]]
            avg_hr = round(sum(hrs) / len(hrs)) if hrs else None
            cads = [p[4] for p in seg if p[4]]
            avg_cad = round(sum(cads) / len(cads)) if cads else None
            alts = [p[3] for p in seg if p[3] is not None]
            gain = sum(max(0.0, b - a) for a, b in zip(alts, alts[1:], strict=False))
            out.append({"km": km, "distance_m": round(meters), "seconds": round(seconds),
                        "elapsed_s": round(seg[-1][0] - pts[0][0]),
                        "pace_s_km": round(seconds / meters * 1000), "avg_hr": avg_hr,
                        "avg_cadence": avg_cad, "elevation_gain_m": round(gain)})  # fmt: skip
            start_i, km = i, km + 1
    return out


def decoupling(time: list, dist: list, hr: list) -> dict | None:
    """Deriva cardiaca: % de pérdida de eficiencia (m/s por ppm) de la 2.ª mitad frente a la 1.ª."""
    pts = [(t, d, hr[i]) for i, (t, d) in enumerate(zip(time, dist, strict=False))
           if t is not None and d is not None and i < len(hr) and hr[i]]  # fmt: skip
    if len(pts) < 10 or pts[-1][0] - pts[0][0] < MIN_DECOUPLING_S:
        return None
    mid = pts[0][0] + (pts[-1][0] - pts[0][0]) / 2
    halves = [[p for p in pts if p[0] <= mid], [p for p in pts if p[0] > mid]]
    efs = []
    for h in halves:
        seconds = h[-1][0] - h[0][0]
        if seconds <= 0:
            return None
        speed = (h[-1][1] - h[0][1]) / seconds
        efs.append(speed / (sum(p[2] for p in h) / len(h)))
    if not efs[0]:
        return None
    pct = round((efs[0] - efs[1]) / efs[0] * 100, 1)
    return {"pct": pct, "first_ef": round(efs[0] * 1000, 2), "second_ef": round(efs[1] * 1000, 2),
            "level": "bien" if pct <= 5 else "alta" if pct <= 10 else "muy alta"}  # fmt: skip


def estimate_vo2max(activity: Activity, hr_rest: float, hr_max: float | None) -> float | None:
    """VO2max orientativo de una carrera sostenida y llana (ACSM + reserva de FC)."""
    duration = activity.moving_duration_s or activity.duration_s
    if not (activity.distance_m and activity.avg_hr and hr_max and duration and duration >= MIN_VO2_SECONDS):
        return None
    if (activity.elevation_gain_m or 0) / (activity.distance_m / 1000) > FLAT_GAIN_PER_KM:
        return None
    hrr = (activity.avg_hr - hr_rest) / (hr_max - hr_rest)
    if not 0.5 <= hrr <= 0.95:
        return None
    vo2 = 0.2 * (activity.distance_m / duration * 60) + 3.5
    value = (vo2 - 3.5) / hrr + 3.5
    return round(value, 1) if 25 <= value <= 85 else None


def _current_vo2max(session: Session, user_id: int) -> tuple[float | None, str | None, str | None]:
    """Último VO2max diario (120 días): primero el del reloj y, si no hay, el de Oura. (valor, día, fuente)."""
    rows = session.exec(
        select(DailyMetric)
        .where(DailyMetric.user_id == user_id)
        .order_by(DailyMetric.day.desc())  # type: ignore[attr-defined]
        .limit(120)
    ).all()
    for key, source in VO2MAX_DAILY:
        for r in rows:
            if (v := (r.metrics or {}).get(key)) is not None:
                return float(v), r.day.isoformat(), source
    return None, None, None


def hr_drift(time: list, hr: list) -> dict | None:
    """Deriva de la FC: % que sube la FC media de la 2.ª mitad frente a la 1.ª (al menos 20 min con pulso)."""
    pts = [(t, h) for t, h in zip(time, hr, strict=False) if t is not None and h]
    if len(pts) < 10 or pts[-1][0] - pts[0][0] < MIN_DRIFT_S:
        return None
    mid = pts[0][0] + (pts[-1][0] - pts[0][0]) / 2
    first = [h for t, h in pts if t <= mid]
    second = [h for t, h in pts if t > mid]
    if not first or not second:
        return None
    a, b = sum(first) / len(first), sum(second) / len(second)
    pct = round((b - a) / a * 100, 1)
    return {"pct": pct, "first_hr": round(a), "second_hr": round(b),
            "level": "bien" if pct <= 5 else "alta" if pct <= 10 else "muy alta"}  # fmt: skip


def trimp(time: list, hr: list, hr_rest: float, hr_max: float | None, sex: Sex | None) -> float | None:
    """TRIMP de Banister con la serie de FC (huecos de más de 30 s fuera)."""
    if not hr_max or hr_max <= hr_rest:
        return None
    a, b = (0.86, 1.67) if sex == Sex.FEMALE else (0.64, 1.92)
    total = 0.0
    for i in range(1, min(len(time), len(hr))):
        h, t0, t1 = hr[i], time[i - 1], time[i]
        if not h or t0 is None or t1 is None or t1 <= t0 or t1 - t0 > MAX_GAP_S:
            continue
        reserve = min(max((h - hr_rest) / (hr_max - hr_rest), 0.0), 1.0)
        total += (t1 - t0) / 60 * reserve * a * math.exp(b * reserve)
    return round(total, 1) if total else None


def heart_rate(activity: Activity, time: list, hr: list, thr: prog.Thresholds, sex: Sex | None) -> dict | None:
    """Pulso de la sesión con la serie de FC: mín./media/máx., % de la FC máx., deriva y TRIMP."""
    values = [h for h in hr if h]
    if len(values) < 2:
        return None
    avg = activity.avg_hr or sum(values) / len(values)
    peak = activity.max_hr or max(values)
    return {
        "avg": round(avg), "min": round(min(values)), "max": round(peak),
        "avg_pct_max": round(avg / thr.hr_max * 100) if thr.hr_max else None,
        "max_pct_max": round(peak / thr.hr_max * 100) if thr.hr_max else None,
        "drift": hr_drift(time, hr),
        "trimp": trimp(time, hr, thr.hr_rest, thr.hr_max, sex),
    }  # fmt: skip


def _gap_by_km(km_splits: list[dict], dist: list, alt: list) -> None:
    """Añade a cada parcial su ritmo ajustado a pendiente (`gap_s_km`; None sin altitud)."""
    pts = [(d, a) for d, a in zip(dist, alt, strict=False) if d is not None and a is not None]
    start = 0.0
    for s in km_splits:
        end = start + s["distance_m"]
        seg = [p for p in pts if start <= p[0] <= end]
        factor = run_metrics.gap_factor([p[0] for p in seg], [p[1] for p in seg])
        s["gap_s_km"] = run_metrics.gap_pace(s["pace_s_km"], factor)
        start = end


def analysis(session: Session, activity: Activity) -> dict:
    """Todo el análisis de la página de la actividad (las partes sin datos van vacías)."""
    from app.services.plan_steps import sport_family
    from app.services.profile import age_on, vo2max_percentile

    ch = load_streams(session, activity.id, ("time", "distance", "hr", "altitude", "cadence", "performance_condition"))
    time, dist, hr, alt, cad = (ch.get(k) or [] for k in ("time", "distance", "hr", "altitude", "cadence"))
    zones, lthr, zone_source = zones_for(session, activity.user_id, activity.sport)
    family = sport_family(activity.sport)
    on_foot = family == "running" or activity.sport in ("walking", "hiking")
    thr = prog.user_thresholds(session, activity.user_id)

    watch = (activity.metrics or {}).get("vo2max")
    estimate = estimate_vo2max(activity, thr.hr_rest, thr.hr_max) if family == "running" and not watch else None
    current, current_day, current_source = _current_vo2max(session, activity.user_id)
    value = watch or estimate
    percentile = None
    profile = session.get(UserProfile, activity.user_id)
    if (current or value) and profile and profile.birth_date and profile.sex:
        percentile = vo2max_percentile(current or value, age_on(profile.birth_date, activity.start_time.date()),
                                       profile.sex)  # fmt: skip
    km_splits = splits(time, dist, hr, alt, cad) if on_foot and dist else []
    _gap_by_km(km_splits, dist, alt)
    load = prog.activity_load(activity, thr)
    return {
        "hr_zones": {
            "zones": time_in_zones(time, hr, zones) if zones and hr else [],
            "lthr": lthr,
            "source": zone_source,
        },
        "vo2max": {
            "activity": value,
            "source": "reloj" if watch else "estimado" if estimate else None,
            "current": current,
            "current_day": current_day,
            "current_source": current_source,
            "percentile": percentile,
        },
        "splits": km_splits,
        "decoupling": decoupling(time, dist, hr) if dist and hr else None,
        "heart_rate": heart_rate(activity, time, hr, thr, profile.sex if profile else None) if hr else None,
        # Carga de cualquier sesión; en carrera, además eficiencia, condición de rendimiento y GAP.
        **(
            run_metrics.summary(session, activity, ch, km_splits, load)
            if family == "running"
            else run_metrics.empty(activity, load)
        ),
    }
