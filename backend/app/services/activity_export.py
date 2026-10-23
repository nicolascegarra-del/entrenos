"""
Exportar una actividad a los formatos que importan las demás apps: FIT, TCX y GPX.

- **FIT**: si la actividad vino de Garmin se entrega el fichero original del reloj (el zip guardado al
  sincronizar). Si no, se genera uno de actividad (file_id, record por segundo, vueltas, sesión y
  actividad) con las series: posición, distancia, altitud, FC, cadencia, potencia y velocidad.
- **TCX** (Garmin Training Center): vueltas con su resumen y puntos con hora, posición, altitud,
  distancia, FC, cadencia y potencia (extensión ActivityExtension v2). Lo importan Strava, TrainingPeaks,
  intervals.icu, COROS, Suunto, Polar…
- **GPX 1.1**: la ruta con hora, altitud y las extensiones de Garmin (FC, cadencia) y la potencia.
  Necesita GPS.

La cadencia de carrera se guarda en pasos/min; FIT y TCX la quieren por pierna (la mitad).
"""

import io
import struct
import zipfile
from datetime import UTC, datetime, timedelta
from xml.sax.saxutils import escape

from sqlmodel import Session, select

from app.models import Activity, ActivityRaw, Lap
from app.services.activity_analysis import load_streams
from app.services.plan_steps import sport_family
from app.services.workout_export import FIT_EPOCH, _crc

CHANNELS = ("time", "distance", "lat", "lon", "altitude", "hr", "cadence", "power", "speed")
FORMATS = ("fit", "tcx", "gpx")
SEMICIRCLE = 2**31 / 180


class ExportError(ValueError):
    """La actividad no se puede exportar en ese formato (p. ej. GPX sin GPS)."""


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _points(activity: Activity, ch: dict[str, list]) -> list[dict]:
    time = ch.get("time") or []
    out = []
    for i, t in enumerate(time):
        if t is None:
            continue
        p = {k: (ch[k][i] if k in ch and i < len(ch[k]) else None) for k in CHANNELS if k != "time"}
        p["when"] = activity.start_time + timedelta(seconds=float(t))
        out.append(p)
    return out


def _per_leg(cadence: float | None, running: bool) -> float | None:
    if cadence is None:
        return None
    return cadence / 2 if running else cadence


def filename(activity: Activity, fmt: str) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in (activity.name or "actividad").lower()).strip("-")[:40]
    return f"{activity.start_time.date().isoformat()}-{safe or 'actividad'}.{fmt}"


# ─── GPX ─────────────────────────────────────────────────────────────────────


def to_gpx(activity: Activity, ch: dict[str, list]) -> bytes:
    points = [p for p in _points(activity, ch) if p["lat"] is not None and p["lon"] is not None]
    if not points:
        raise ExportError("Esta actividad no tiene GPS: expórtala en TCX o FIT.")
    running = sport_family(activity.sport) == "running"
    rows = []
    for p in points:
        ext = []
        if p["hr"]:
            ext.append(f"<gpxtpx:hr>{round(p['hr'])}</gpxtpx:hr>")
        if (cad := _per_leg(p["cadence"], running)) is not None:
            ext.append(f"<gpxtpx:cad>{round(cad)}</gpxtpx:cad>")
        power = f"<power>{round(p['power'])}</power>" if p["power"] is not None else ""
        ele = f"<ele>{p['altitude']:.1f}</ele>" if p["altitude"] is not None else ""
        extensions = (
            f"<extensions>{power}<gpxtpx:TrackPointExtension>{''.join(ext)}</gpxtpx:TrackPointExtension></extensions>"
            if ext or power else ""
        )  # fmt: skip
        rows.append(
            f'<trkpt lat="{p["lat"]:.7f}" lon="{p["lon"]:.7f}">{ele}<time>{_iso(p["when"])}</time>{extensions}</trkpt>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="APP ENTRENOS" xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">'
        f"<metadata><name>{escape(activity.name or 'Actividad')}</name>"
        f"<time>{_iso(activity.start_time)}</time></metadata>"
        f"<trk><name>{escape(activity.name or 'Actividad')}</name><type>{escape(activity.sport)}</type>"
        f"<trkseg>{''.join(rows)}</trkseg></trk></gpx>"
    ).encode()


# ─── TCX ─────────────────────────────────────────────────────────────────────


def _tcx_sport(sport: str) -> str:
    family = sport_family(sport)
    return "Running" if family == "running" else "Biking" if family == "cycling" else "Other"


def _laps(session: Session, activity: Activity) -> list[Lap]:
    laps = list(session.exec(select(Lap).where(Lap.activity_id == activity.id).order_by(Lap.index)).all())
    if laps:
        return laps
    return [Lap(activity_id=activity.id, index=0, start_offset_s=0, duration_s=activity.duration_s,
                distance_m=activity.distance_m, avg_hr=activity.avg_hr, max_hr=activity.max_hr)]  # fmt: skip


def to_tcx(session: Session, activity: Activity, ch: dict[str, list]) -> bytes:
    running = sport_family(activity.sport) == "running"
    points = _points(activity, ch)
    laps = _laps(session, activity)
    out = []
    for k, lap in enumerate(laps):
        start = activity.start_time + timedelta(seconds=lap.start_offset_s)
        end = laps[k + 1].start_offset_s if k + 1 < len(laps) else float("inf")
        track = []
        for p in points:
            offset = (p["when"] - activity.start_time).total_seconds()
            if not lap.start_offset_s <= offset < end:
                continue
            parts = [f"<Time>{_iso(p['when'])}</Time>"]
            if p["lat"] is not None and p["lon"] is not None:
                parts.append(f"<Position><LatitudeDegrees>{p['lat']:.7f}</LatitudeDegrees>"
                             f"<LongitudeDegrees>{p['lon']:.7f}</LongitudeDegrees></Position>")  # fmt: skip
            if p["altitude"] is not None:
                parts.append(f"<AltitudeMeters>{p['altitude']:.1f}</AltitudeMeters>")
            if p["distance"] is not None:
                parts.append(f"<DistanceMeters>{p['distance']:.1f}</DistanceMeters>")
            if p["hr"]:
                parts.append(f"<HeartRateBpm><Value>{round(p['hr'])}</Value></HeartRateBpm>")
            cad = _per_leg(p["cadence"], running)
            if cad is not None and not running:
                parts.append(f"<Cadence>{round(cad)}</Cadence>")
            ext = []
            if p["speed"] is not None:
                ext.append(f"<ns3:Speed>{p['speed']:.3f}</ns3:Speed>")
            if cad is not None and running:
                ext.append(f"<ns3:RunCadence>{round(cad)}</ns3:RunCadence>")
            if p["power"] is not None:
                ext.append(f"<ns3:Watts>{round(p['power'])}</ns3:Watts>")
            if ext:
                parts.append(f"<Extensions><ns3:TPX>{''.join(ext)}</ns3:TPX></Extensions>")
            track.append(f"<Trackpoint>{''.join(parts)}</Trackpoint>")
        summary = [f"<TotalTimeSeconds>{lap.duration_s:.1f}</TotalTimeSeconds>",
                   f"<DistanceMeters>{(lap.distance_m or 0):.1f}</DistanceMeters>"]  # fmt: skip
        if lap.avg_hr:
            summary.append(f"<AverageHeartRateBpm><Value>{round(lap.avg_hr)}</Value></AverageHeartRateBpm>")
        if lap.max_hr:
            summary.append(f"<MaximumHeartRateBpm><Value>{round(lap.max_hr)}</Value></MaximumHeartRateBpm>")
        if k == 0 and activity.calories:
            summary.append(f"<Calories>{round(activity.calories)}</Calories>")
        summary.append("<Intensity>Active</Intensity><TriggerMethod>Manual</TriggerMethod>")
        out.append(f'<Lap StartTime="{_iso(start)}">{"".join(summary)}<Track>{"".join(track)}</Track></Lap>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" '
        'xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">'
        f'<Activities><Activity Sport="{_tcx_sport(activity.sport)}"><Id>{_iso(activity.start_time)}</Id>'
        f"{''.join(out)}<Notes>{escape(activity.name or '')}</Notes></Activity></Activities>"
        '<Author xsi:type="Application_t" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<Name>APP ENTRENOS</Name></Author></TrainingCenterDatabase>"
    ).encode()


# ─── FIT ─────────────────────────────────────────────────────────────────────

_BASE = {"enum": (0x00, "B", 0xFF), "uint8": (0x02, "B", 0xFF), "uint16": (0x84, "H", 0xFFFF),
         "uint32": (0x86, "I", 0xFFFFFFFF), "sint32": (0x85, "i", 0x7FFFFFFF)}  # fmt: skip
_FIT_SPORT = {"running": 1, "cycling": 2, "swimming": 5, "walking": 11, "hiking": 17, "strength": 10}


class _Writer:
    def __init__(self) -> None:
        self.body, self.local = b"", 0

    def message(self, num: int, fields: list[tuple[int, str]], rows: list[list[float | None]]) -> None:
        local = self.local
        self.local += 1
        defs = b"".join(struct.pack("BBB", n, struct.calcsize(_BASE[k][1]), _BASE[k][0]) for n, k in fields)
        self.body += struct.pack("<BBBHB", 0x40 | local, 0, 0, num, len(fields)) + defs
        for row in rows:
            data = struct.pack("B", local)
            for (_, kind), value in zip(fields, row, strict=True):
                _, fmt, invalid = _BASE[kind]
                data += struct.pack("<" + fmt, invalid if value is None else int(round(value)))
            self.body += data

    def bytes(self) -> bytes:
        header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(self.body), b".FIT")
        header += struct.pack("<H", _crc(header))
        data = header + self.body
        return data + struct.pack("<H", _crc(data))


def _fit_time(t: datetime) -> int:
    return int((t.astimezone(UTC) - FIT_EPOCH).total_seconds())


def original_fit(session: Session, activity: Activity) -> bytes | None:
    """El .FIT original del reloj (Garmin), si se guardó al sincronizar."""
    from app.services.storage import get_storage

    raw = session.get(ActivityRaw, activity.id)
    if raw is None or not raw.fit_object_key:
        return None
    data = get_storage().get(raw.fit_object_key)
    if not data:
        return None
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            name = next((n for n in zf.namelist() if n.lower().endswith(".fit")), None)
            return zf.read(name) if name else None
    return data if data[8:12] == b".FIT" else None


def to_fit(session: Session, activity: Activity, ch: dict[str, list]) -> bytes:
    if (original := original_fit(session, activity)) is not None:
        return original
    family = sport_family(activity.sport)
    running = family == "running"
    sport = _FIT_SPORT.get(family, _FIT_SPORT.get(activity.sport, 0))
    start = _fit_time(activity.start_time)
    w = _Writer()
    w.message(0, [(0, "enum"), (1, "uint16"), (2, "uint16"), (4, "uint32")], [[4, 255, 1, start]])
    rec_fields = [(253, "uint32"), (0, "sint32"), (1, "sint32"), (5, "uint32"), (2, "uint16"), (3, "uint8"),
                  (4, "uint8"), (7, "uint16"), (6, "uint16")]  # fmt: skip
    rows = []
    for p in _points(activity, ch):
        rows.append([
            _fit_time(p["when"]),
            p["lat"] * SEMICIRCLE if p["lat"] is not None else None,
            p["lon"] * SEMICIRCLE if p["lon"] is not None else None,
            p["distance"] * 100 if p["distance"] is not None else None,
            (p["altitude"] + 500) * 5 if p["altitude"] is not None else None,
            p["hr"] or None,
            _per_leg(p["cadence"], running),
            p["power"],
            p["speed"] * 1000 if p["speed"] is not None else None,
        ])  # fmt: skip
    if rows:
        w.message(20, rec_fields, rows)
    end = start + round(activity.duration_s)
    lap_fields = [(253, "uint32"), (2, "uint32"), (7, "uint32"), (8, "uint32"), (9, "uint32"), (15, "uint8"),
                  (16, "uint8"), (254, "uint16")]  # fmt: skip
    laps = _laps(session, activity)
    w.message(19, lap_fields, [[
        start + round(lap.start_offset_s + lap.duration_s), start + round(lap.start_offset_s), lap.duration_s * 1000,
        lap.duration_s * 1000, (lap.distance_m or 0) * 100, lap.avg_hr, lap.max_hr, k,
    ] for k, lap in enumerate(laps)])  # fmt: skip
    moving = activity.moving_duration_s or activity.duration_s
    sess_fields = [(253, "uint32"), (2, "uint32"), (5, "enum"), (7, "uint32"), (8, "uint32"), (9, "uint32"),
                   (11, "uint16"), (16, "uint8"), (17, "uint8"), (22, "uint16"), (26, "uint16")]  # fmt: skip
    w.message(18, sess_fields, [[end, start, sport, activity.duration_s * 1000, moving * 1000,
                                 (activity.distance_m or 0) * 100, activity.calories, activity.avg_hr,
                                 activity.max_hr, activity.elevation_gain_m, len(laps)]])  # fmt: skip
    # activity: timestamp, total_timer_time, num_sessions, type (manual), event (activity), event_type (stop)
    w.message(34, [(253, "uint32"), (0, "uint32"), (1, "uint16"), (2, "enum"), (3, "enum"), (4, "enum")],
              [[end, moving * 1000, 1, 0, 26, 1]])  # fmt: skip
    return w.bytes()


def export(session: Session, activity: Activity, fmt: str) -> tuple[bytes, str, str]:
    """
    Fichero de la actividad.

    Returns:
        (contenido, tipo MIME, nombre de fichero)

    Raises:
        ExportError: formato desconocido o sin datos para él.
    """
    if fmt not in FORMATS:
        raise ExportError("Formato no válido: usa fit, tcx o gpx.")
    ch = load_streams(session, activity.id, CHANNELS)
    if fmt == "gpx":
        return to_gpx(activity, ch), "application/gpx+xml", filename(activity, "gpx")
    if fmt == "tcx":
        return to_tcx(session, activity, ch), "application/vnd.garmin.tcx+xml", filename(activity, "tcx")
    return to_fit(session, activity, ch), "application/vnd.ant.fit", filename(activity, "fit")
