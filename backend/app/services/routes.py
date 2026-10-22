"""
Recorridos repetidos y comparador de actividades.

- Huella del recorrido: 64 puntos GPS remuestreados a distancias iguales (se guarda en
  `Activity.metrics["route_sig"]`). Dos actividades son el mismo recorrido si su distancia se parece
  (±12 %), empiezan y acaban cerca (< 250 m) y la separación entre sus huellas, buscando el punto
  más cercano en una ventana alrededor de cada posición, es < 100 m de media y < 150 m en el 90 %. Tiene en cuenta el
  sentido: el mismo circuito al revés es otro recorrido (los tiempos no son comparables).
- Agrupación voraz por orden cronológico: cada recorrido lo representa su primera actividad.
- Comparador: dos actividades alineadas por distancia (tiempo, ritmo, FC y altitud cada pocos
  metros), diferencia de tiempo acumulada, parciales por km y los dos trazados para el mapa.
"""

import bisect
import math
from collections import Counter
from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from app.models import Activity, ActivityStream
from app.services import progress as prog
from app.services.es_format import num
from app.services.plan_steps import local_day, sport_family

SIG_KEY = "route_sig"
SIG_VERSION = 1
SIG_POINTS = 64
MIN_DISTANCE_M = 1000
MATCH_DIST_RATIO = 0.12
MATCH_ENDS_M = 250
MATCH_MEAN_M = 100
MATCH_P90_M = 150
WINDOW = 5  # índices de margen al buscar el punto más cercano (± ~8 % del recorrido)
EARTH_R = 6_371_000


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia en metros entre dos puntos (lat, lon)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def _track(lat: list, lon: list, dist: list | None) -> tuple[list[tuple[float, float]], list[float]]:
    """Puntos válidos con su distancia acumulada (la del reloj o, si falta, calculada por GPS)."""
    pts: list[tuple[float, float]] = []
    cum: list[float] = []
    for i, (la, lo) in enumerate(zip(lat, lon, strict=False)):
        if la is None or lo is None:
            continue
        d = dist[i] if dist and i < len(dist) and dist[i] is not None else None
        if d is None:
            d = (cum[-1] + haversine(pts[-1], (la, lo))) if pts else 0.0
        if cum and d < cum[-1]:  # la distancia nunca retrocede
            d = cum[-1]
        pts.append((la, lo))
        cum.append(d)
    return pts, cum


def resample(pts: list[tuple[float, float]], cum: list[float], n: int = SIG_POINTS) -> list[list[float]] | None:
    """`n` puntos a distancias iguales a lo largo del recorrido (interpolando entre muestras)."""
    if len(pts) < 2 or cum[-1] - cum[0] < MIN_DISTANCE_M:
        return None
    out = []
    for k in range(n):
        target = cum[0] + (cum[-1] - cum[0]) * k / (n - 1)
        i = min(bisect.bisect_left(cum, target), len(cum) - 1)
        if i == 0 or cum[i] == cum[i - 1]:
            la, lo = pts[i]
        else:
            f = (target - cum[i - 1]) / (cum[i] - cum[i - 1])
            la = pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f
            lo = pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f
        out.append([round(la, 6), round(lo, 6)])
    return out


def _load_channels(session: Session, activity_id: int, channels: list[str]) -> dict[str, list]:
    rows = session.exec(select(ActivityStream).where(
        ActivityStream.activity_id == activity_id, col(ActivityStream.channel).in_(channels)
    )).all()  # fmt: skip
    return {r.channel: r.values for r in rows}


def signature(session: Session, activity: Activity) -> list[list[float]] | None:
    """Huella guardada o calculada ahora (también se guarda cuando no hay GPS, para no repetir)."""
    cached = (activity.metrics or {}).get(SIG_KEY)
    if isinstance(cached, dict) and cached.get("v") == SIG_VERSION:
        return cached.get("pts")
    ch = _load_channels(session, activity.id, ["lat", "lon", "distance"])
    pts, cum = _track(ch.get("lat", []), ch.get("lon", []), ch.get("distance"))
    sig = resample(pts, cum)
    activity.metrics = {**(activity.metrics or {}), SIG_KEY: {"v": SIG_VERSION, "pts": sig}}
    session.add(activity)
    return sig


def deviations(a: list[list[float]], b: list[list[float]]) -> list[float]:
    """Para cada punto de `a`, distancia (m) al más cercano de `b` dentro de la ventana."""
    out = []
    for i, p in enumerate(a):
        lo, hi = max(0, i - WINDOW), min(len(b), i + WINDOW + 1)
        out.append(min(haversine((p[0], p[1]), (q[0], q[1])) for q in b[lo:hi]))
    return out


def mean_deviation(a: list[list[float]], b: list[list[float]]) -> float:
    d = deviations(a, b)
    return sum(d) / len(d)


def same_route(a: list[list[float]], dist_a: float, b: list[list[float]], dist_b: float) -> bool:
    """
    Mismo recorrido si la distancia se parece, empiezan y acaban cerca y las huellas se separan poco:
    de media (< MATCH_MEAN_M) y también en el 90 % de los puntos (< MATCH_P90_M). El percentil evita
    que un desvío largo (salir del estadio por la ciudad) quede escondido en la media.
    """
    if not dist_a or not dist_b or abs(dist_a - dist_b) / max(dist_a, dist_b) > MATCH_DIST_RATIO:
        return False
    if haversine(tuple(a[0]), tuple(b[0])) > MATCH_ENDS_M or haversine(tuple(a[-1]), tuple(b[-1])) > MATCH_ENDS_M:
        return False
    for x, y in ((a, b), (b, a)):
        d = sorted(deviations(x, y))
        if sum(d) / len(d) >= MATCH_MEAN_M or d[int(len(d) * 0.9)] >= MATCH_P90_M:
            return False
    return True


# ─── Agrupar recorridos ──────────────────────────────────────────────────────


@dataclass
class RouteGroup:
    rep: Activity
    sig: list[list[float]]
    members: list[Activity] = field(default_factory=list)


def group_routes(session: Session, user_id: int) -> list[RouteGroup]:
    """Recorridos con al menos dos actividades del mismo tipo de deporte, del más repetido al menos."""
    activities = [a for a in prog.user_activities(session, user_id) if (a.distance_m or 0) >= MIN_DISTANCE_M]
    groups: list[RouteGroup] = []
    for a in activities:
        sig = signature(session, a)
        if sig is None:
            continue
        family = sport_family(a.sport)
        match = next((g for g in groups if sport_family(g.rep.sport) == family
                      and same_route(g.sig, g.rep.distance_m or 0, sig, a.distance_m or 0)), None)  # fmt: skip
        if match is None:
            groups.append(RouteGroup(rep=a, sig=sig, members=[a]))
        else:
            match.members.append(a)
    session.commit()  # guarda las huellas calculadas
    repeated = [g for g in groups if len(g.members) >= 2]
    return sorted(repeated, key=lambda g: (len(g.members), g.members[-1].start_time), reverse=True)


def _pace(a: Activity) -> float | None:
    seconds = a.moving_duration_s or a.duration_s
    return seconds / (a.distance_m / 1000) if a.distance_m else None


def effort(a: Activity) -> dict:
    return {
        "activity_id": a.id,
        "day": local_day(a.start_time, a.timezone),
        "name": a.name,
        "duration_s": a.moving_duration_s or a.duration_s,
        "distance_m": a.distance_m,
        "pace_s_km": _pace(a),
        "avg_hr": a.avg_hr,
        "elevation_gain_m": a.elevation_gain_m,
    }


def group_out(g: RouteGroup, session: Session | None = None) -> dict:
    """Resumen del recorrido; el mejor esfuerzo es el de mejor ritmo (las distancias varían un poco)."""
    names = Counter(a.name for a in g.members if a.name)
    km = (g.rep.distance_m or 0) / 1000
    efforts = [effort(a) for a in g.members]
    ranked = sorted((e for e in efforts if e["pace_s_km"]), key=lambda e: e["pace_s_km"])
    out = {
        "id": g.rep.id,
        # Garmin suele llamar igual a todo («Cartagena Carrera»): la distancia los distingue.
        "name": f"{names.most_common(1)[0][0]} · {num(km, 1)} km" if names else f"Recorrido de {num(km, 1)} km",
        "sport": g.rep.sport,
        "distance_m": g.rep.distance_m,
        "count": len(g.members),
        "best": ranked[0] if ranked else None,
        "last": efforts[-1],
        "first_day": efforts[0]["day"],
    }
    if session is not None:  # detalle: todos los intentos y el trazado real de la primera actividad
        out["efforts"] = efforts
        out["track"] = _route_points(_load_channels(session, g.rep.id, ["lat", "lon"])) or g.sig
    return out


def route_for_activity(session: Session, user_id: int, activity_id: int) -> dict | None:
    """El recorrido al que pertenece una actividad (con su posición en el ranking) o None."""
    for g in group_routes(session, user_id):
        if any(a.id == activity_id for a in g.members):
            out = group_out(g, session)
            ranked = sorted((e for e in out["efforts"] if e["pace_s_km"]), key=lambda e: e["pace_s_km"])
            out["rank"] = next((i + 1 for i, e in enumerate(ranked) if e["activity_id"] == activity_id), None)
            return out
    return None


# ─── Comparador ──────────────────────────────────────────────────────────────

COMPARE_CHANNELS = ["time", "distance", "hr", "altitude", "lat", "lon"]
MAX_GRID = 400
PACE_WINDOW_M = 100


def _series(ch: dict[str, list]) -> tuple[list[float], dict[str, list[float | None]]]:
    """Distancia acumulada (monótona) y los canales en esos mismos índices."""
    dist, time = ch.get("distance", []), ch.get("time", [])
    idx = [i for i in range(min(len(dist), len(time))) if dist[i] is not None and time[i] is not None]
    d: list[float] = []
    keep: list[int] = []
    for i in idx:
        if d and dist[i] < d[-1]:
            continue
        d.append(dist[i])
        keep.append(i)
    return d, {
        name: [vals[i] if i < len(vals) else None for i in keep] for name, vals in ch.items() if name != "distance"
    }


def _interp(d: list[float], values: list[float | None], x: float) -> float | None:
    i = bisect.bisect_left(d, x)
    if i <= 0:
        return values[0] if values else None
    if i >= len(d):
        return values[-1]
    a, b = values[i - 1], values[i]
    if a is None or b is None:
        return a if b is None else b
    if d[i] == d[i - 1]:
        return b
    return a + (b - a) * (x - d[i - 1]) / (d[i] - d[i - 1])


def _splits(d: list[float], t: list[float | None], until: float) -> list[float | None]:
    """Tiempo de cada km completo."""
    out = []
    for km in range(1, int(until // 1000) + 1):
        t0, t1 = _interp(d, t, (km - 1) * 1000), _interp(d, t, km * 1000)
        out.append(round(t1 - t0, 1) if t0 is not None and t1 is not None else None)
    return out


def _route_points(ch: dict[str, list], n: int = 300) -> list[list[float]]:
    pts = [
        (la, lo)
        for la, lo in zip(ch.get("lat", []), ch.get("lon", []), strict=False)
        if la is not None and lo is not None
    ]
    step = max(1, len(pts) // n)
    return [[round(p[0], 6), round(p[1], 6)] for p in pts[::step]]


def compare(session: Session, a: Activity, b: Activity) -> dict:
    """Dos actividades alineadas por distancia: diferencia acumulada (b − a), ritmo, FC, altitud y km."""
    ca, cb = _load_channels(session, a.id, COMPARE_CHANNELS), _load_channels(session, b.id, COMPARE_CHANNELS)
    da, sa = _series(ca)
    db, sb = _series(cb)
    until = min(da[-1] if da else 0, db[-1] if db else 0)
    points = []
    if until > 0:
        step = max(25.0, until / MAX_GRID)
        x = 0.0
        while x <= until:
            row: dict[str, float | None] = {"distance_m": round(x)}
            for tag, d, s in (("a", da, sa), ("b", db, sb)):
                times = s.get("time", [])
                t = _interp(d, times, x)
                row[f"time_{tag}"] = t
                row[f"hr_{tag}"] = _interp(d, s["hr"], x) if s.get("hr") else None
                row[f"alt_{tag}"] = _interp(d, s["altitude"], x) if s.get("altitude") else None
                # Ritmo en una ventana de ±PACE_WINDOW_M (suaviza el ruido del GPS), en s/km.
                lo, hi = max(0.0, x - PACE_WINDOW_M), min(until, x + PACE_WINDOW_M)
                t_lo, t_hi = _interp(d, times, lo), _interp(d, times, hi)
                ok = t_lo is not None and t_hi is not None and hi > lo
                row[f"pace_{tag}"] = round((t_hi - t_lo) / (hi - lo) * 1000, 1) if ok else None
            ta, tb = row["time_a"], row["time_b"]
            row["gap_s"] = round(tb - ta, 1) if ta is not None and tb is not None else None
            points.append(row)
            x += step
    splits_a, splits_b = _splits(da, sa.get("time", []), until), _splits(db, sb.get("time", []), until)
    return {
        "a": effort(a),
        "b": effort(b),
        "distance_m": round(until),
        "points": points,
        "splits": [
            {"km": i + 1, "a": sa_, "b": sb_, "diff": round(sb_ - sa_, 1) if sa_ and sb_ else None}
            for i, (sa_, sb_) in enumerate(zip(splits_a, splits_b, strict=False))
        ],  # fmt: skip
        "track_a": _route_points(ca),
        "track_b": _route_points(cb),
    }
