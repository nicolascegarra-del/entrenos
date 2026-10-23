"""
Apple Watch / Apple Salud: importar el `export.zip` de la app Salud y recibir envíos de un Atajo de iOS.

Apple no ofrece una API web para leer Salud, así que hay dos vías:

- **Export completo** (Salud → tu foto → «Exportar todos los datos de salud»): un zip con `export.xml`
  (puede pesar varios GB) y las rutas GPS en `workout-routes/*.gpx`. Se lee en streaming en una sola pasada:
  los registros de pulso se guardan en dos arrays compactos para reconstruir la serie de cada entreno, y
  las métricas diarias (FC en reposo, HRV, sueño, pasos) se agregan por día.
- **Atajo** (automatización diaria en el iPhone): manda los entrenos recientes y el pulso en JSON a
  `/ingest/apple-shortcuts` con el mismo token personal que Health Connect. Ver `ingest_shortcut`.

Nada sobrescribe lo que ya trae Garmin u otro reloj: los entrenos se deduplican en `save_imported` y las
métricas diarias solo se rellenan si ese día no tenía valor.
"""

import re
import unicodedata
import zipfile
from array import array
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import IO, Any
from xml.etree.ElementTree import iterparse  # noqa: S405 - se rechazan ENTITY antes de parsear

from sqlmodel import Session, select

from app.models import Activity, DailyMetric
from app.services.file_import import (
    FileImportError,
    ImportedActivity,
    _local,
    _num,
    _summary_from_points,
    _time,
    _xml,
    after_import,
    save_imported,
)

SOURCE = "apple"
HR_MATCH_S = 10  # pulso más cercano a cada punto GPS
VO2_LOOKBACK_DAYS = 7

# Tipo de entreno de HealthKit (sin el prefijo HKWorkoutActivityType) → deporte de la app.
WORKOUT_TYPES = {
    "running": "running", "cycling": "cycling", "walking": "walking", "hiking": "hiking",
    "swimming": "lap_swimming", "traditionalstrengthtraining": "strength_training",
    "functionalstrengthtraining": "strength_training", "coretraining": "strength_training",
    "highintensityintervaltraining": "hiit", "crosstraining": "hiit", "mixedcardio": "cardio",
    "elliptical": "elliptical", "rowing": "rowing", "yoga": "yoga", "pilates": "pilates",
    "stairclimbing": "stair_climbing", "stairs": "stair_climbing", "dance": "dance",
    "cooldown": "other", "other": "other",
}  # fmt: skip
SPORT_LABEL = {
    "running": "Carrera", "treadmill_running": "Carrera en cinta", "trail_running": "Trail",
    "cycling": "Ciclismo", "indoor_cycling": "Ciclismo en interior", "walking": "Caminata",
    "hiking": "Senderismo", "lap_swimming": "Natación", "open_water_swimming": "Natación en aguas abiertas",
    "strength_training": "Fuerza", "hiit": "HIIT", "yoga": "Yoga", "elliptical": "Elíptica",
}  # fmt: skip
# Palabras (sin tildes, en minúscula) que llegan del Atajo en español o inglés → deporte.
SHORTCUT_WORDS = (
    ("cinta", "treadmill_running"), ("treadmill", "treadmill_running"), ("trail", "trail_running"),
    ("correr", "running"), ("carrera", "running"), ("running", "running"), ("run", "running"),
    ("ciclismo en interior", "indoor_cycling"), ("indoor cycling", "indoor_cycling"),
    ("ciclismo", "cycling"), ("bici", "cycling"), ("cycling", "cycling"),
    ("caminar", "walking"), ("caminata", "walking"), ("walk", "walking"),
    ("senderismo", "hiking"), ("hiking", "hiking"), ("aguas abiertas", "open_water_swimming"),
    ("open water", "open_water_swimming"), ("natacion", "lap_swimming"), ("swim", "lap_swimming"),
    ("fuerza", "strength_training"), ("strength", "strength_training"), ("intervalos", "hiit"),
    ("hiit", "hiit"), ("eliptica", "elliptical"), ("elliptical", "elliptical"), ("remo", "rowing"),
    ("rowing", "rowing"), ("yoga", "yoga"), ("pilates", "pilates"),
)  # fmt: skip

DISTANCE_UNITS = {"m": 1.0, "km": 1000.0, "mi": 1609.344, "ft": 0.3048, "yd": 0.9144}
ENERGY_UNITS = {"kcal": 1.0, "cal": 1.0, "kj": 1 / 4.184, "j": 1 / 4184}
DURATION_UNITS = {"min": 60.0, "s": 1.0, "sec": 1.0, "h": 3600.0, "hr": 3600.0}
ASLEEP = ("asleep",)  # AsleepCore, AsleepDeep, AsleepREM, AsleepUnspecified y el antiguo «Asleep»


def _apple_time(value: str | None) -> datetime | None:
    """«2024-05-01 07:30:00 +0200» (formato del export) o ISO 8601."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return _time(value)


def _offset(t: datetime) -> str | None:
    """Offset «+02:00» de una fecha con zona, como guarda Garmin en `Activity.timezone`."""
    off = t.utcoffset()
    if off is None:
        return None
    minutes = int(off.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def _with_unit(value: str | None, unit: str | None, table: dict[str, float]) -> float | None:
    number = _num(value)
    if number is None:
        return None
    return number * table.get((unit or "").strip().lower(), 1.0)


def workout_sport(raw: str | None, metadata: dict[str, str] | None = None) -> str:
    """Deporte de la app a partir del tipo de HealthKit y de si fue en interior o en aguas abiertas."""
    key = (raw or "").removeprefix("HKWorkoutActivityType").lower()
    sport = WORKOUT_TYPES.get(key, key or "other")
    meta = metadata or {}
    indoor = meta.get("HKIndoorWorkout") == "1"
    if sport == "running" and indoor:
        return "treadmill_running"
    if sport == "cycling" and indoor:
        return "indoor_cycling"
    if sport == "lap_swimming" and meta.get("HKSwimmingLocationType") == "2":
        return "open_water_swimming"
    return sport


def shortcut_sport(raw: Any) -> str:
    """Deporte a partir del texto que da el Atajo («Correr», «Running», «HKWorkoutActivityTypeCycling»…)."""
    text = str(raw or "").strip()
    if text.startswith("HKWorkoutActivityType"):
        return workout_sport(text)
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return next((sport for word, sport in SHORTCUT_WORDS if word in plain), "other")


# ─── Pulso ───────────────────────────────────────────────────────────────────


@dataclass
class HeartRate:
    """Serie de pulso de todo el export, ordenada por tiempo (epoch en segundos)."""

    times: array = field(default_factory=lambda: array("d"))
    bpm: array = field(default_factory=lambda: array("d"))
    _sorted: bool = True

    def add(self, t: datetime, value: float) -> None:
        ts = t.timestamp()
        if self.times and ts < self.times[-1]:
            self._sorted = False
        self.times.append(ts)
        self.bpm.append(value)

    def finish(self) -> None:
        if not self._sorted:
            pairs = sorted(zip(self.times, self.bpm, strict=True))
            self.times = array("d", (p[0] for p in pairs))
            self.bpm = array("d", (p[1] for p in pairs))
            self._sorted = True

    def window(self, start: datetime, end: datetime) -> list[tuple[float, float]]:
        lo = bisect_left(self.times, start.timestamp())
        hi = bisect_right(self.times, end.timestamp())
        return [(self.times[i], self.bpm[i]) for i in range(lo, hi)]


def _nearest(samples: list[tuple[float, float]], ts: float) -> float | None:
    if not samples:
        return None
    i = bisect_left(samples, (ts, -1.0))
    best = min((samples[j] for j in (i - 1, i) if 0 <= j < len(samples)), key=lambda s: abs(s[0] - ts))
    return best[1] if abs(best[0] - ts) <= HR_MATCH_S else None


def _gpx_points(text: str) -> list[dict]:
    """Puntos (hora, lat, lon, altitud) de una ruta GPX de Apple Salud."""
    root = _xml(text)
    points = []
    for el in root.iter():
        if _local(el.tag) != "trkpt":
            continue
        p: dict = {"lat": _num(el.attrib.get("lat")), "lon": _num(el.attrib.get("lon"))}
        for sub in el:
            st = _local(sub.tag)
            if st == "ele":
                p["ele"] = _num(sub.text)
            elif st == "time":
                p["time"] = _time(sub.text)
        points.append(p)
    return points


# ─── Entrenos del export ─────────────────────────────────────────────────────


@dataclass
class AppleWorkout:
    sport: str
    start: datetime
    end: datetime
    duration_s: float
    distance_m: float | None = None
    calories: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_gain_m: float | None = None
    route: str | None = None  # ruta del GPX dentro del zip
    source_name: str = ""

    @property
    def external_id(self) -> str:
        return f"{self.sport}:{self.start.astimezone(UTC).isoformat()}"


def parse_workout(attrib: dict[str, str], children: list[tuple[str, dict[str, str]]]) -> AppleWorkout | None:
    """Un `<Workout>` del export (con sus `WorkoutStatistics`, `MetadataEntry` y `WorkoutRoute`)."""
    start, end = _apple_time(attrib.get("startDate")), _apple_time(attrib.get("endDate"))
    if start is None or end is None:
        return None
    metadata = {a.get("key", ""): a.get("value", "") for tag, a in children if tag == "MetadataEntry"}
    duration = _with_unit(attrib.get("duration"), attrib.get("durationUnit") or "min", DURATION_UNITS)
    w = AppleWorkout(
        sport=workout_sport(attrib.get("workoutActivityType"), metadata),
        start=start,
        end=end,
        duration_s=duration or (end - start).total_seconds(),
        distance_m=_with_unit(attrib.get("totalDistance"), attrib.get("totalDistanceUnit"), DISTANCE_UNITS),
        calories=_with_unit(attrib.get("totalEnergyBurned"), attrib.get("totalEnergyBurnedUnit"), ENERGY_UNITS),
        source_name=attrib.get("sourceName", "")[:80],
    )
    for tag, a in children:
        kind = a.get("type", "")
        if tag == "WorkoutStatistics":
            if kind.endswith("HeartRate"):
                w.avg_hr, w.max_hr = _num(a.get("average")), _num(a.get("maximum"))
            elif "Distance" in kind and w.distance_m is None:
                w.distance_m = _with_unit(a.get("sum"), a.get("unit"), DISTANCE_UNITS)
            elif kind.endswith("ActiveEnergyBurned") and w.calories is None:
                w.calories = _with_unit(a.get("sum"), a.get("unit"), ENERGY_UNITS)
        elif tag == "FileReference" and a.get("path", "").endswith(".gpx"):
            w.route = a["path"].lstrip("/")
    if gain := metadata.get("HKElevationAscended"):
        number, _, unit = gain.partition(" ")
        meters = _with_unit(number, unit, {"cm": 0.01, "m": 1.0, "ft": 0.3048})
        w.elevation_gain_m = round(meters) if meters is not None else None
    return w if w.duration_s > 0 else None


def to_imported(w: AppleWorkout, hr: HeartRate | None, route_text: str | None) -> ImportedActivity:
    """Actividad con series: ruta GPS + pulso si hay ruta; si no, la serie de pulso sola."""
    samples = hr.window(w.start, w.end) if hr else []
    act: ImportedActivity | None = None
    if route_text:
        try:
            points = _gpx_points(route_text)
            for p in points:
                if p.get("time"):
                    p["hr"] = _nearest(samples, p["time"].timestamp())
            act = _summary_from_points(points, w.sport)
        except FileImportError:
            act = None
    if act is None and len(samples) >= 2:
        points = [{"time": datetime.fromtimestamp(t, UTC), "hr": bpm} for t, bpm in samples]
        act = _summary_from_points(points, w.sport)
        act.streams = {k: v for k, v in act.streams.items() if k in ("time", "hr")}
        act.moving_duration_s = None
    if act is None:
        act = ImportedActivity(sport=w.sport, start_time=w.start.astimezone(UTC), duration_s=w.duration_s)
    hrs = [b for _, b in samples]
    # El resumen de Apple manda sobre lo calculado de los puntos.
    act.sport = w.sport
    act.start_time = w.start.astimezone(UTC)
    act.duration_s = w.duration_s
    act.distance_m = w.distance_m if w.distance_m else act.distance_m
    act.calories = w.calories
    act.avg_hr = w.avg_hr or (round(sum(hrs) / len(hrs)) if hrs else None)
    act.max_hr = w.max_hr or (max(hrs) if hrs else None)
    act.elevation_gain_m = w.elevation_gain_m if w.elevation_gain_m is not None else act.elevation_gain_m
    act.timezone = _offset(w.start)
    act.name = SPORT_LABEL.get(w.sport, "Entreno") + " · Apple Watch"
    return act


# ─── Métricas diarias ────────────────────────────────────────────────────────


@dataclass
class Daily:
    """Agregados por día. Pasos y sueño por fuente (iPhone y reloj cuentan lo mismo): se queda la mayor."""

    resting_hr: dict[date, float] = field(default_factory=dict)
    hrv_sdnn: dict[date, list[float]] = field(default_factory=lambda: defaultdict(list))
    vo2max: dict[date, float] = field(default_factory=dict)
    steps: dict[tuple[date, str], float] = field(default_factory=lambda: defaultdict(float))
    sleep: dict[tuple[date, str], float] = field(default_factory=lambda: defaultdict(float))

    def add_record(self, a: dict[str, str], hr: HeartRate) -> None:
        kind = a.get("type", "")
        start = _apple_time(a.get("startDate"))
        if start is None:
            return
        if kind == "HKQuantityTypeIdentifierHeartRate":
            if (v := _num(a.get("value"))) is not None:
                hr.add(start, v)
        elif kind == "HKQuantityTypeIdentifierRestingHeartRate":
            if (v := _num(a.get("value"))) is not None:
                self.resting_hr[start.date()] = v
        elif kind == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":
            if (v := _num(a.get("value"))) is not None:
                self.hrv_sdnn[start.date()].append(v)
        elif kind == "HKQuantityTypeIdentifierVO2Max":
            if (v := _num(a.get("value"))) is not None:
                self.vo2max[start.date()] = v
        elif kind == "HKQuantityTypeIdentifierStepCount":
            if (v := _num(a.get("value"))) is not None:
                self.steps[(start.date(), a.get("sourceName", ""))] += v
        elif kind == "HKCategoryTypeIdentifierSleepAnalysis":
            end = _apple_time(a.get("endDate"))
            if end and any(s in a.get("value", "").lower() for s in ASLEEP):
                self.sleep[(end.date(), a.get("sourceName", ""))] += (end - start).total_seconds()

    def by_day(self) -> dict[date, dict[str, float]]:
        out: dict[date, dict[str, float]] = defaultdict(dict)
        for day, v in self.resting_hr.items():
            out[day]["resting_hr"] = v
        for day, values in self.hrv_sdnn.items():
            # Apple mide SDNN (Garmin, RMSSD): escalas distintas, por eso va en su propia clave.
            out[day]["hrv_sdnn"] = round(sum(values) / len(values), 1)
        for key, per_source in (("steps_daily", self.steps), ("sleep_seconds", self.sleep)):
            for (day, _), v in per_source.items():
                out[day][key] = max(out[day].get(key, 0), round(v))
        return out


def save_daily(session: Session, user_id: int, days: dict[date, dict[str, float]]) -> int:
    """Rellena métricas diarias sin pisar lo que ya hubiera (de Garmin, por ejemplo). Devuelve los días tocados."""
    if not days:
        return 0
    rows = {
        r.day: r
        for r in session.exec(
            select(DailyMetric).where(DailyMetric.user_id == user_id, DailyMetric.day.in_(list(days)))  # type: ignore[attr-defined]
        ).all()
    }
    touched = 0
    for day, values in days.items():
        row = rows.get(day) or DailyMetric(user_id=user_id, day=day)
        metrics = dict(row.metrics or {})
        new = {k: v for k, v in values.items() if metrics.get(k) is None}
        if new:
            row.metrics = {**metrics, **new}
            session.add(row)
            touched += 1
    session.commit()
    return touched


def _vo2_for(vo2: dict[date, float], day: date) -> float | None:
    for back in range(VO2_LOOKBACK_DAYS + 1):
        if (v := vo2.get(day - timedelta(days=back))) is not None:
            return v
    return None


# ─── Lectura del export ──────────────────────────────────────────────────────


class _Counting:
    """Envuelve el flujo del XML para saber cuánto se lleva leído (barra de progreso)."""

    def __init__(self, raw: IO[bytes]) -> None:
        self.raw, self.read_bytes = raw, 0

    def read(self, n: int = -1) -> bytes:
        chunk = self.raw.read(n)
        self.read_bytes += len(chunk)
        return chunk


def _check_header(raw: IO[bytes]) -> bytes:
    """Lee la cabecera (con el DTD interno de Apple) y rechaza ENTITY: evita la «bomba» de entidades."""
    head = raw.read(256 * 1024)
    if re.search(rb"<!ENTITY", head, re.IGNORECASE):
        raise FileImportError("El export no puede incluir declaraciones ENTITY.")
    if b"<HealthData" not in head:
        raise FileImportError("No parece un export de Apple Salud (falta <HealthData>).")
    return head


class _Prefixed:
    """Devuelve primero la cabecera ya leída y luego el resto del flujo."""

    def __init__(self, head: bytes, rest: _Counting) -> None:
        self.head, self.rest = head, rest

    def read(self, n: int = -1) -> bytes:
        if self.head:
            out, self.head = (self.head, b"") if n < 0 or n >= len(self.head) else (self.head[:n], self.head[n:])
            return out
        return self.rest.read(n)


def read_export(
    stream: IO[bytes], progress: Callable[[int], None] | None = None, total: int = 0
) -> tuple[list[AppleWorkout], HeartRate, Daily]:
    """
    Recorre `export.xml` una vez: entrenos, serie de pulso y métricas diarias.

    Args:
        stream: el XML (sin descomprimir).
        progress: se llama con el % leído (aprox. cada 1 %).
        total: tamaño del XML en bytes, para el %.
    """
    counting = _Counting(stream)
    source = _Prefixed(_check_header(counting), counting)
    workouts: list[AppleWorkout] = []
    hr, daily = HeartRate(), Daily()
    depth, last_pct = 0, -1
    root = None
    children: list[tuple[str, dict[str, str]]] = []
    in_workout = False
    for event, el in iterparse(source, events=("start", "end")):  # noqa: S314 - ENTITY rechazado arriba
        if event == "start":
            depth += 1
            if root is None:
                root = el
            if depth == 2 and el.tag == "Workout":
                in_workout, children = True, []
            continue
        depth -= 1
        if in_workout and depth >= 2:
            children.append((el.tag, dict(el.attrib)))
            continue
        if depth != 1:
            continue
        if el.tag == "Record":
            daily.add_record(el.attrib, hr)
        elif el.tag == "Workout":
            in_workout = False
            if (w := parse_workout(dict(el.attrib), children)) is not None:
                workouts.append(w)
        root.clear()  # type: ignore[union-attr] - no acumular el árbol en memoria
        if progress and total:
            pct = min(99, counting.read_bytes * 100 // total)
            if pct != last_pct:
                last_pct = pct
                progress(pct)
    hr.finish()
    return workouts, hr, daily


def import_export(
    session: Session, user_id: int, path: Path, progress: Callable[[int], None] | None = None
) -> dict[str, int]:
    """
    Importa un `export.zip` (o el `export.xml` suelto) de Apple Salud.

    Returns:
        Entrenos nuevos, ya existentes (de Garmin u otro reloj) y días con métricas añadidas.

    Raises:
        FileImportError: si el fichero no es un export de Salud.
    """
    routes: dict[str, str] = {}
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            member = next(
                (i for i in zf.infolist() if i.filename.endswith("export.xml") and "cda" not in i.filename), None
            )
            if member is None:
                raise FileImportError("El zip no tiene export.xml: ¿es el export de la app Salud?")
            with zf.open(member) as xml:
                workouts, hr, daily = read_export(xml, progress, member.file_size)
            names = {i.filename.split("/apple_health_export/", 1)[-1]: i.filename for i in zf.infolist()}
            for w in workouts:
                if w.route and (name := names.get(w.route) or names.get(f"apple_health_export/{w.route}")):
                    info = zf.getinfo(name)
                    if info.file_size <= 20_000_000:
                        routes[w.route] = zf.read(info).decode("utf-8", "replace")
    else:
        with path.open("rb") as xml:
            workouts, hr, daily = read_export(xml, progress, path.stat().st_size)
    counts = save_workouts(session, user_id, workouts, hr, routes, daily.vo2max)
    counts["days"] = save_daily(session, user_id, daily.by_day())
    return counts


def save_workouts(
    session: Session,
    user_id: int,
    workouts: list[AppleWorkout],
    hr: HeartRate | None,
    routes: dict[str, str],
    vo2max: dict[date, float],
) -> dict[str, int]:
    counts = {"workouts": 0, "duplicates": 0}
    for w in workouts:
        act = to_imported(w, hr, routes.get(w.route or ""))
        activity, created = save_imported(session, user_id, act, SOURCE, w.external_id)
        if not created:
            counts["duplicates"] += 1
            continue
        counts["workouts"] += 1
        if w.sport.endswith("running") and (v := _vo2_for(vo2max, w.start.date())) is not None:
            activity.metrics = {**(activity.metrics or {}), "vo2max": v}
            session.add(activity)
            session.commit()
    if counts["workouts"]:
        after_import(session, user_id)
    return counts


# ─── Atajo de iOS ────────────────────────────────────────────────────────────

MAX_ITEMS = 2000
MAX_HR = 100_000


def _number(value: Any) -> float | None:
    """Números del Atajo: 5.2, «5,2», «5,2 km»…"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value or ""))
    return float(m.group().replace(",", ".")) if m else None


def _seconds(value: Any) -> float | None:
    """Duración en segundos, «1:02:03», «45:10» o «45 min»."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").strip().lower()
    if re.fullmatch(r"\d+(:\d{1,2}){1,2}", text):
        parts = [int(p) for p in text.split(":")]
        return float(sum(p * 60**i for i, p in enumerate(reversed(parts))))
    number = _number(text)
    if number is None:
        return None
    if "h" in text and "min" not in text:
        return number * 3600
    return number * 60 if "min" in text else number


def _distance_m(value: Any, unit: Any = None) -> float | None:
    number = _number(value)
    if number is None:
        return None
    text = f"{value} {unit or ''}".lower()
    for name, factor in (("km", 1000.0), ("mi", 1609.344), (" m", 1.0)):
        if name in text:
            return number * factor
    return number * 1000 if number < 300 else number  # sin unidad: km si es pequeño, metros si no


def _list(payload: dict, *keys: str) -> list:
    for k in keys:
        if isinstance(v := payload.get(k), list):
            return v
    return []


def _columns(payload: dict, key: str, names: tuple[str, ...]) -> list[dict]:
    """
    El Atajo puede mandar una lista de objetos o columnas paralelas (más fácil de montar sin bucles):
    `{"workouts": {"type": [...], "start": [...], ...}}`.
    """
    value = payload.get(key)
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    if isinstance(value, dict):
        cols = {n: value[n] for n in names if isinstance(value.get(n), list)}
        if not cols:
            return []
        size = max(len(c) for c in cols.values())
        return [{n: (c[i] if i < len(c) else None) for n, c in cols.items()} for i in range(size)]
    return []


def _pick(raw: dict, *keys: str) -> Any:
    """Primer valor no vacío entre varias claves (el Atajo puede usar nombres en inglés o en español)."""
    return next((raw[k] for k in keys if raw.get(k) not in (None, "")), None)


def ingest_shortcut(session: Session, user_id: int, payload: dict) -> dict[str, int]:
    """
    Entrenos (y pulso, FC en reposo, sueño) enviados por el Atajo de iOS.

    Formato (claves en inglés o español; fechas ISO 8601 o «2024-05-01 07:30:00 +0200»):

        {"workouts": [{"type": "Correr", "start": "...", "end": "...", "duration": 2700,
                       "distance": "8,2 km", "energy": 610, "avg_hr": 151, "max_hr": 172}],
         "heart_rate": {"dates": [...], "values": [...]},
         "resting_hr": [{"date": "...", "value": 48}], "sleep": [{"start": "...", "end": "..."}]}

    Returns:
        Entrenos nuevos, duplicados y días con métricas añadidas.
    """
    hr = HeartRate()
    for s in _columns(payload, "heart_rate", ("dates", "values", "date", "value"))[:MAX_HR]:
        t = _apple_time(str(s.get("dates") or s.get("date") or s.get("time") or ""))
        v = _number(s.get("values", s.get("value", s.get("bpm"))))
        if t and v:
            hr.add(t, v)
    hr.finish()
    workouts = []
    names = ("type", "tipo", "start", "inicio", "end", "fin", "duration", "duracion", "distance", "distancia",
             "energy", "energia", "avg_hr", "max_hr", "source")  # fmt: skip
    for raw in _columns(payload, "workouts", names)[:MAX_ITEMS]:
        start = _apple_time(str(_pick(raw, "start", "inicio", "start_date") or ""))
        end = _apple_time(str(_pick(raw, "end", "fin", "end_date") or ""))
        span = (end - start).total_seconds() if start and end else None
        duration = _seconds(_pick(raw, "duration", "duracion")) or span
        if start is None or not duration or duration <= 0:
            continue
        workouts.append(
            AppleWorkout(
                sport=shortcut_sport(_pick(raw, "type", "tipo")),
                start=start,
                end=end or start + timedelta(seconds=duration),
                duration_s=duration,
                distance_m=_distance_m(_pick(raw, "distance", "distancia"), _pick(raw, "distance_unit")),
                calories=_number(_pick(raw, "energy", "energia", "calories")),
                avg_hr=_number(_pick(raw, "avg_hr", "fc_media")),
                max_hr=_number(_pick(raw, "max_hr", "fc_max")),
                source_name=str(_pick(raw, "source", "fuente") or "")[:80],
            )
        )
    counts = save_workouts(session, user_id, workouts, hr, {}, {})
    daily = Daily()
    for r in _list(payload, "resting_hr", "fc_reposo")[:MAX_ITEMS]:
        if isinstance(r, dict) and (t := _apple_time(str(r.get("date") or ""))) and (v := _number(r.get("value"))):
            daily.resting_hr[t.date()] = v
    for s in _list(payload, "sleep", "sueno")[:MAX_ITEMS]:
        if not isinstance(s, dict):
            continue
        start, end = _apple_time(str(s.get("start") or "")), _apple_time(str(s.get("end") or ""))
        if start and end and end > start and "inbed" not in str(s.get("value", "")).lower().replace(" ", ""):
            daily.sleep[(end.date(), "atajo")] += (end - start).total_seconds()
    counts["days"] = save_daily(session, user_id, daily.by_day())
    return counts


def latest_import_activity(session: Session, user_id: int) -> Activity | None:
    """Último entreno que llegó de Apple (para el estado en Ajustes)."""
    return session.exec(
        select(Activity)
        .where(Activity.user_id == user_id, Activity.source == SOURCE)
        .order_by(Activity.created_at.desc())  # type: ignore[attr-defined]
    ).first()
