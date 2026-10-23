"""
Importar actividades de cualquier reloj: ficheros FIT (todas las marcas), GPX y TCX, y la capa común
para guardarlas (la usan también COROS y Health Connect).

- Se normaliza todo a `ImportedActivity`: resumen + series por canal (time, distance, lat, lon,
  altitude, hr, cadence, speed), las mismas que vienen de Garmin.
- Deduplicado entre fuentes: si ya hay una actividad que empieza a ±2 min y dura ±5 %, no se crea otra
  (el mismo entreno puede llegar de Garmin y de un fichero, o de dos relojes).
- Los XML se rechazan si traen DOCTYPE o ENTITY (protección frente a XXE / «billion laughs»).
"""

import io
import math
import re
import xml.etree.ElementTree as ET  # noqa: N817
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, col, select

from app.models import Activity, ActivityStream, Lap
from app.services.routes import haversine

MAX_FILE_BYTES = 25_000_000
SOURCE_NAMES = {
    "coros": "Actividad de COROS",
    "health_connect": "Actividad de Health Connect",
    "apple": "Entreno de Apple Watch",
}
DEDUP_START_S = 120
DEDUP_DURATION = 0.05
SEMICIRCLE = 180 / 2**31

# Deporte de FIT / Health Connect / COROS → los nombres que usa la app (los de Garmin).
SPORTS = {
    "running": "running", "run": "running", "trail_running": "trail_running", "treadmill": "treadmill_running",
    "cycling": "cycling", "biking": "cycling", "road_biking": "road_biking", "mountain_biking": "mountain_biking",
    "indoor_cycling": "indoor_cycling", "swimming": "lap_swimming", "lap_swimming": "lap_swimming",
    "training": "strength_training", "strength_training": "strength_training", "walking": "walking",
    "hiking": "hiking", "exercise_type_running": "running", "exercise_type_biking": "cycling",
    "exercise_type_walking": "walking", "exercise_type_hiking": "hiking",
    "exercise_type_strength_training": "strength_training",
}  # fmt: skip


class FileImportError(ValueError):
    """El fichero no se puede importar (formato desconocido, dañado o sin datos)."""


@dataclass
class ImportedActivity:
    sport: str
    start_time: datetime
    duration_s: float
    moving_duration_s: float | None = None
    distance_m: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_gain_m: float | None = None
    calories: float | None = None
    name: str = ""
    timezone: str | None = None  # offset local «+02:00», si la fuente lo sabe
    streams: dict[str, list[float | None]] = field(default_factory=dict)
    # Como Garmin: métricas con claves del catálogo (avg_power, aerobic_te…) y vueltas (`Lap`).
    metrics: dict[str, float] = field(default_factory=dict)
    laps: list[dict] = field(default_factory=list)


def sport_name(raw: str | None) -> str:
    key = (raw or "").strip().lower().replace(" ", "_")
    return SPORTS.get(key, key or "other")


# ─── Series → resumen ────────────────────────────────────────────────────────


def _summary_from_points(points: list[dict], sport: str, name: str = "") -> ImportedActivity:
    """Resumen y series a partir de puntos con time (datetime), lat, lon, ele, hr, cad, dist opcionales."""
    points = [p for p in points if p.get("time") is not None]
    if len(points) < 2:
        raise FileImportError("El fichero no tiene puntos con hora: no se puede importar.")
    points.sort(key=lambda p: p["time"])
    t0 = points[0]["time"]
    time, dist, lat, lon, alt, hr, cad = [], [], [], [], [], [], []
    d = 0.0
    prev = None
    for p in points:
        if p.get("dist") is not None:
            d = float(p["dist"])
        elif prev is not None and p.get("lat") is not None and prev.get("lat") is not None:
            d += haversine((prev["lat"], prev["lon"]), (p["lat"], p["lon"]))
        if p.get("lat") is not None:
            prev = p
        time.append((p["time"] - t0).total_seconds())
        dist.append(round(d, 1))
        lat.append(p.get("lat"))
        lon.append(p.get("lon"))
        alt.append(p.get("ele"))
        hr.append(p.get("hr"))
        cad.append(p.get("cad"))
    speed: list[float | None] = [None]
    for i in range(1, len(time)):
        dt = time[i] - time[i - 1]
        speed.append(round((dist[i] - dist[i - 1]) / dt, 3) if dt > 0 else None)
    streams = {"time": time, "distance": dist, "speed": speed}
    for name_, values in (("lat", lat), ("lon", lon), ("altitude", alt), ("hr", hr), ("cadence", cad)):
        if any(v is not None for v in values):
            streams[name_] = values
    hrs = [v for v in hr if v]
    alts = [v for v in alt if v is not None]
    gain = sum(max(0.0, b - a) for a, b in zip(alts, alts[1:], strict=False)) if alts else None
    moving = sum(time[i] - time[i - 1] for i in range(1, len(time)) if (speed[i] or 0) > 0.5)
    return ImportedActivity(
        sport=sport,
        start_time=t0.astimezone(UTC),
        duration_s=time[-1],
        moving_duration_s=moving or None,
        distance_m=round(d, 1) or None,
        avg_hr=round(sum(hrs) / len(hrs)) if hrs else None,
        max_hr=max(hrs) if hrs else None,
        elevation_gain_m=round(gain) if gain is not None else None,
        name=name,
        streams=streams,
    )


# ─── FIT ─────────────────────────────────────────────────────────────────────


def parse_fit(data: bytes) -> ImportedActivity:
    """FIT (Garmin, COROS, Suunto, Polar, Wahoo, Amazfit…): sesión + registros por segundo."""
    from fitparse import FitFile, FitParseError

    try:
        fit = FitFile(io.BytesIO(data))
        fit.parse()
    except (FitParseError, ValueError, KeyError, IndexError) as exc:
        raise FileImportError("El fichero FIT está dañado o no es un FIT válido.") from exc
    session_msg = next(iter(fit.get_messages("session")), None)
    s = {f.name: f.value for f in session_msg} if session_msg else {}
    sport = sport_name(s.get("sport") if isinstance(s.get("sport"), str) else None)
    running = "running" in sport or sport in ("walking", "hiking")
    points = []
    for rec in fit.get_messages("record"):
        v = {f.name: f.value for f in rec}
        lat, lon = v.get("position_lat"), v.get("position_long")
        ts = v.get("timestamp")
        points.append({
            "time": ts.replace(tzinfo=UTC) if isinstance(ts, datetime) and ts.tzinfo is None else ts,
            "lat": lat * SEMICIRCLE if lat is not None else None,
            "lon": lon * SEMICIRCLE if lon is not None else None,
            "ele": v.get("enhanced_altitude", v.get("altitude")),
            "hr": v.get("heart_rate"),
            "cad": _cadence(v.get("cadence"), v.get("fractional_cadence"), running),
            "dist": v.get("distance"),
        })  # fmt: skip
    if len([p for p in points if p["time"]]) < 2:
        # Sin registros (p. ej. fuerza): solo el resumen de la sesión.
        start = s.get("start_time")
        if not isinstance(start, datetime) or not s.get("total_elapsed_time"):
            raise FileImportError("El FIT no tiene una sesión de actividad.")
        return ImportedActivity(
            sport=sport,
            start_time=start.replace(tzinfo=UTC),
            duration_s=float(s["total_elapsed_time"]),
            moving_duration_s=s.get("total_timer_time"),
            distance_m=s.get("total_distance"),
            avg_hr=s.get("avg_heart_rate"),
            max_hr=s.get("max_heart_rate"),
            elevation_gain_m=s.get("total_ascent"),
            calories=s.get("total_calories"),
            metrics=_fit_metrics(s, running),
            laps=_fit_laps(fit, start.replace(tzinfo=UTC), running),
        )
    act = _summary_from_points(points, sport)
    # El resumen del reloj manda sobre lo calculado (pausas, desnivel filtrado, calorías).
    for attr, key in (("duration_s", "total_elapsed_time"), ("moving_duration_s", "total_timer_time"),
                      ("distance_m", "total_distance"), ("avg_hr", "avg_heart_rate"), ("max_hr", "max_heart_rate"),
                      ("elevation_gain_m", "total_ascent"), ("calories", "total_calories")):  # fmt: skip
        if s.get(key) is not None:
            setattr(act, attr, float(s[key]))
    act.metrics = _fit_metrics(s, running)
    act.laps = _fit_laps(fit, act.start_time, running)
    return act


def _cadence(value: float | None, fraction: float | None, running: bool) -> float | None:
    """En FIT la cadencia de carrera va por pierna (zancadas/min): la app usa pasos/min, como Garmin."""
    if value is None:
        return None
    return round((value + (fraction or 0)) * 2, 1) if running else value


def _first(d: dict, *keys: str) -> float | None:
    return next((float(d[k]) for k in keys if isinstance(d.get(k), int | float)), None)


def _fit_metrics(s: dict, running: bool) -> dict[str, float]:
    """Métricas de la sesión FIT con las claves del catálogo (las mismas que trae Garmin)."""
    out: dict[str, float] = {}
    cad = _first(s, "avg_running_cadence", "avg_cadence")
    if cad is not None:
        out["avg_cadence"] = _cadence(cad, s.get("avg_fractional_cadence"), running) or cad
    for key, fields in (("avg_power", ("avg_power",)), ("normalized_power", ("normalized_power",)),
                        ("aerobic_te", ("total_training_effect",)),
                        ("anaerobic_te", ("total_anaerobic_training_effect",)),
                        ("training_load", ("training_load_peak", "training_stress_score")),
                        ("steps", ("total_strides",))):  # fmt: skip
        if (value := _first(s, *fields)) is not None:
            out[key] = value
    if running and "steps" in out:
        out["steps"] *= 2  # total_strides cuenta zancadas (dos pasos)
    if (step := _first(s, "avg_step_length")) is not None:
        out["avg_stride_length"] = round(step / 10, 1)  # mm → cm, como Garmin
    if (max_speed := _first(s, "enhanced_max_speed", "max_speed")) is not None:
        out["max_speed"] = max_speed
    return out


def _fit_laps(fit, start: datetime, running: bool) -> list[dict]:
    """Vueltas FIT → filas `Lap` (mismos campos y métricas que las de Garmin)."""
    laps = []
    for index, msg in enumerate(fit.get_messages("lap")):
        v = {f.name: f.value for f in msg}
        lap_start = v.get("start_time")
        if isinstance(lap_start, datetime) and lap_start.tzinfo is None:
            lap_start = lap_start.replace(tzinfo=UTC)
        metrics: dict[str, float] = {}
        cad = _first(v, "avg_running_cadence", "avg_cadence")
        if cad is not None:
            metrics["avg_cadence"] = _cadence(cad, v.get("avg_fractional_cadence"), running) or cad
        for key, fields in (("avg_power", ("avg_power",)), ("normalized_power", ("normalized_power",)),
                            ("elevation_gain_m", ("total_ascent",)), ("elevation_loss_m", ("total_descent",)),
                            ("max_speed", ("enhanced_max_speed", "max_speed"))):  # fmt: skip
            if (value := _first(v, *fields)) is not None:
                metrics[key] = value
        if (step := _first(v, "avg_step_length")) is not None:
            metrics["avg_stride_length"] = round(step / 10, 1)
        laps.append({
            "index": index,
            "start_offset_s": max((lap_start - start).total_seconds(), 0.0) if isinstance(lap_start, datetime) else 0.0,
            "duration_s": _first(v, "total_timer_time", "total_elapsed_time") or 0.0,
            "distance_m": _first(v, "total_distance"),
            "avg_hr": _first(v, "avg_heart_rate"),
            "max_hr": _first(v, "max_heart_rate"),
            "avg_speed": _first(v, "enhanced_avg_speed", "avg_speed"),
            "metrics": metrics,
        })  # fmt: skip
    return laps


# ─── GPX y TCX ───────────────────────────────────────────────────────────────


def _xml(text: str) -> ET.Element:
    if re.search(r"<!(DOCTYPE|ENTITY)", text[:5000], re.IGNORECASE):
        raise FileImportError("El fichero no puede incluir declaraciones DOCTYPE ni ENTITY.")
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise FileImportError("El fichero XML está dañado.") from exc


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        t = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _num(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "") else None
    except ValueError:
        return None


def parse_gpx(text: str) -> ImportedActivity:
    """GPX de una actividad (con hora en cada punto; FC y cadencia de las extensiones de Garmin)."""
    root = _xml(text)
    name, sport = "", None
    points = []
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "trk":
            for child in el:
                if _local(child.tag) == "name" and child.text:
                    name = child.text.strip()
                elif _local(child.tag) == "type" and child.text:
                    sport = child.text
        elif tag == "trkpt":
            p = {"lat": _num(el.attrib.get("lat")), "lon": _num(el.attrib.get("lon"))}
            for sub in el.iter():
                st = _local(sub.tag)
                if st == "ele":
                    p["ele"] = _num(sub.text)
                elif st == "time":
                    p["time"] = _time(sub.text)
                elif st in ("hr", "heartrate"):
                    p["hr"] = _num(sub.text)
                elif st in ("cad", "cadence"):
                    p["cad"] = _num(sub.text)
            points.append(p)
    return _summary_from_points(points, sport_name(sport or "running"), name)


def parse_tcx(text: str) -> ImportedActivity:
    """TCX (Garmin Training Center): Trackpoint con hora, posición, altitud, distancia y FC."""
    root = _xml(text)
    sport = None
    points = []
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "Activity":
            sport = el.attrib.get("Sport")
        elif tag == "Trackpoint":
            p: dict = {}
            for sub in el.iter():
                st = _local(sub.tag)
                if st == "Time":
                    p["time"] = _time(sub.text)
                elif st == "LatitudeDegrees":
                    p["lat"] = _num(sub.text)
                elif st == "LongitudeDegrees":
                    p["lon"] = _num(sub.text)
                elif st == "AltitudeMeters":
                    p["ele"] = _num(sub.text)
                elif st == "DistanceMeters":
                    p["dist"] = _num(sub.text)
                elif st == "HeartRateBpm":
                    value = next((c for c in sub if _local(c.tag) == "Value"), None)
                    p["hr"] = _num(value.text) if value is not None else None
                elif st in ("Cadence", "RunCadence"):
                    p["cad"] = _num(sub.text)
            points.append(p)
    return _summary_from_points(points, sport_name(sport or "running"))


def parse_file(filename: str, data: bytes) -> tuple[ImportedActivity, str]:
    """Elige el lector por extensión (o por contenido) y devuelve la actividad y su tipo."""
    if len(data) > MAX_FILE_BYTES:
        raise FileImportError("El fichero es demasiado grande (máximo 25 MB).")
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "fit" or data[8:12] == b".FIT":
        return parse_fit(data), "fit"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FileImportError("Formato no reconocido: sube un FIT, GPX o TCX.") from exc
    if ext == "tcx" or "<TrainingCenterDatabase" in text[:2000]:
        return parse_tcx(text), "tcx"
    if ext == "gpx" or "<gpx" in text[:2000]:
        return parse_gpx(text), "gpx"
    raise FileImportError("Formato no reconocido: sube un FIT, GPX o TCX.")


# ─── Guardar ─────────────────────────────────────────────────────────────────


def find_duplicate(session: Session, user_id: int, act: ImportedActivity) -> Activity | None:
    """Actividad ya existente del mismo entreno (inicio ±2 min y duración ±5 %), venga de donde venga."""
    window = timedelta(seconds=DEDUP_START_S)
    rows = session.exec(select(Activity).where(
        Activity.user_id == user_id,
        col(Activity.start_time) >= act.start_time - window,
        col(Activity.start_time) <= act.start_time + window,
    )).all()  # fmt: skip
    for a in rows:
        longest = max(a.duration_s, act.duration_s) or 1
        if abs(a.duration_s - act.duration_s) / longest <= DEDUP_DURATION:
            return a
    return None


def save_imported(session: Session, user_id: int, act: ImportedActivity, source: str,
                  external_id: str | None = None) -> tuple[Activity, bool]:  # fmt: skip
    """
    Crea la actividad con sus series. Si ya existe (mismo origen e id, o el mismo entreno de otra fuente)
    devuelve la existente.

    Returns:
        (actividad, creada)
    """
    if external_id:
        same = session.exec(select(Activity).where(
            Activity.user_id == user_id, Activity.source == source, Activity.external_id == external_id
        )).first()  # fmt: skip
        if same is not None:
            return same, False
    dup = find_duplicate(session, user_id, act)
    if dup is not None:
        return dup, False
    activity = Activity(
        user_id=user_id, sport=act.sport, name=act.name or SOURCE_NAMES.get(source, ""),
        start_time=act.start_time, timezone=act.timezone,
        duration_s=act.duration_s, moving_duration_s=act.moving_duration_s, distance_m=act.distance_m,
        avg_hr=act.avg_hr, max_hr=act.max_hr, elevation_gain_m=act.elevation_gain_m, calories=act.calories,
        source=source, external_id=external_id,
    )  # fmt: skip
    activity.metrics = {**(activity.metrics or {}), **act.metrics}
    session.add(activity)
    session.flush()
    for lap in act.laps:
        session.add(Lap(activity_id=activity.id, **lap))
    for channel, values in act.streams.items():
        if values and not all(v is None or (isinstance(v, float) and math.isnan(v)) for v in values):
            session.add(ActivityStream(activity_id=activity.id, channel=channel, values=_floats(values)))
    session.commit()
    session.refresh(activity)
    return activity, True


def _floats(values: list) -> list[float | None]:
    """La columna es un array de float: un FIT puede mezclar enteros y decimales (o NaN) en la misma serie."""
    out: list[float | None] = []
    for v in values:
        if v is None or isinstance(v, bool):
            out.append(None)
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(None if math.isnan(f) or math.isinf(f) else f)
    return out


def after_import(session: Session, user_id: int) -> None:
    """Lo mismo que tras sincronizar Garmin: zonas, zapatilla por defecto y logros (nunca rompe la importación)."""
    from app.services.achievements import evaluate
    from app.services.gear import assign_default
    from app.services.plan_service import match_pending
    from app.services.zones import refresh_zones

    # Emparejar con el plan primero: si era una sesión de test, se analiza y cuenta para las zonas.
    for fn in (match_pending, refresh_zones, assign_default, evaluate):
        try:
            fn(session, user_id)
        except Exception:  # noqa: BLE001
            session.rollback()
    try:
        from app.services.activity_review import queue_reviews

        queue_reviews(session, user_id, datetime.now(UTC) - timedelta(minutes=15))
    except Exception:  # noqa: BLE001 - el análisis es secundario
        session.rollback()
