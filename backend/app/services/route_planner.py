"""
Planificador de rutas (como el de COROS): marcas inicio, fin y puntos de paso en el mapa y la ruta va por
carreteras o senderos, con sus km, desnivel, perfil de altura, superficies y un tiempo estimado.

- **Motor**: openrouteservice (ORS, datos de OpenStreetMap). Perfiles a pie, senderismo y bici, y devuelve la
  altitud de cada punto. Clave gratuita en openrouteservice.org (`ORS_API_KEY`); la llamada va siempre desde el
  backend para no exponerla.
- **Caché** en Redis por puntos y modo (7 días): mover la vista o deshacer no gasta cuota.
- **Tiempo estimado**: ritmo fácil del atleta (VDOT de sus entrenos, o 6:00/km), más lento en sendero y
  corregido por pendiente (subir cuesta, bajar ahorra algo). En bici, velocidades típicas por terreno.
"""

import contextlib
import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import date
from html import escape

import httpx
import redis
from sqlmodel import Session

from app.core.config import get_settings

log = logging.getLogger(__name__)

ORS_URL = "https://api.openrouteservice.org"
TIMEOUT = 15.0
MAX_POINTS = 25
MAX_GEOMETRY = 600  # puntos que se guardan y se pintan (la ruta se simplifica)
PROFILE_POINTS = 200  # puntos del perfil de altura
CACHE_SECONDS = 7 * 86400

MODES = {
    "asfalto": "foot-walking",
    "trail": "foot-hiking",
    "bici": "cycling-regular",
    "mtb": "cycling-mountain",
}
MODE_LABELS = {"asfalto": "Asfalto", "trail": "Trail", "bici": "Bici", "mtb": "MTB"}
DEFAULT_EASY_PACE = 360  # s/km sin datos del atleta
TRAIL_FACTOR = 1.15  # el sendero es más lento a igual esfuerzo
BIKE_SPEED_KMH = {"bici": 22.0, "mtb": 14.0}

# Códigos de superficie y tipo de vía de ORS agrupados en lo que interesa a quien corre.
SURFACE_GROUPS = {
    "Asfalto o pavimento": {1, 3, 4, 5, 6, 7, 14},
    "Tierra, grava o pista": {2, 8, 9, 10, 11, 12, 15, 16, 17, 18},
}
WAYTYPE_GROUPS = {
    "Carretera o calle": {1, 2, 3},
    "Sendero o camino": {4, 7, 8},
    "Pista": {5},
    "Carril bici": {6},
}


class RouteError(ValueError):
    """La ruta no se puede calcular (mensaje para la persona)."""


@dataclass
class Waypoint:
    lat: float
    lon: float


def _redis() -> redis.Redis | None:
    try:
        return redis.Redis.from_url(get_settings().redis_url, socket_timeout=2, decode_responses=True)
    except redis.RedisError:
        return None


def _cache_key(points: list[Waypoint], mode: str) -> str:
    raw = json.dumps([mode, [(round(p.lat, 5), round(p.lon, 5)) for p in points]])
    return "route-plan:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _ors_post(path: str, body: dict) -> dict:
    key = get_settings().ors_api_key
    if not key:
        raise RouteError("El planificador de rutas no está configurado (falta la clave de openrouteservice).")
    try:
        with httpx.Client(timeout=TIMEOUT, headers={"Authorization": key, "User-Agent": "ktrain"}) as http:
            res = http.post(f"{ORS_URL}{path}", json=body)
    except httpx.HTTPError as exc:
        raise RouteError("No se pudo contactar con el servicio de rutas. Prueba en un momento.") from exc
    if res.status_code == 429:
        raise RouteError("Se ha agotado el cupo de rutas por hoy. Prueba más tarde.")
    if res.status_code >= 400:
        message = ""
        with contextlib.suppress(ValueError):
            message = str(res.json().get("error", {}).get("message", ""))
        log.info("ORS %s: %s", res.status_code, message[:200])
        if "Could not find routable point" in message or "routable" in message:
            raise RouteError("Algún punto está lejos de cualquier camino: acércalo a una calle o sendero.")
        if "distance" in message.lower() and "exceed" in message.lower():
            raise RouteError("La ruta es demasiado larga para calcularla de una vez: divídela en dos.")
        raise RouteError("No se ha encontrado un camino entre esos puntos con este modo.")
    return res.json()


def _simplify(coords: list[list[float]], limit: int) -> list[list[float]]:
    if len(coords) <= limit:
        return coords
    step = (len(coords) - 1) / (limit - 1)
    return [coords[round(i * step)] for i in range(limit)]


def _groups(summary: list[dict], groups: dict[str, set[int]]) -> list[dict]:
    totals: dict[str, float] = {}
    for item in summary:
        name = next((g for g, codes in groups.items() if int(item.get("value", -1)) in codes), "Otros o sin datos")
        totals[name] = totals.get(name, 0.0) + float(item.get("distance", 0))
    total = sum(totals.values()) or 1
    return sorted(
        ({"tipo": k, "distancia_m": round(v), "pct": round(v / total * 100)} for k, v in totals.items() if v > 0),
        key=lambda x: -x["distancia_m"],
    )


def parse_ors(data: dict) -> dict:
    """Geometría [lat, lon, alt], distancia, desnivel, perfil de altura y superficies de la respuesta de ORS."""
    try:
        feature = data["features"][0]
    except (KeyError, IndexError) as exc:
        raise RouteError("No se ha encontrado un camino entre esos puntos.") from exc
    raw = feature["geometry"]["coordinates"]  # [lon, lat, alt]
    props = feature.get("properties", {})
    pts = [(c[1], c[0], c[2] if len(c) > 2 else None) for c in raw]
    cumulative = [0.0]
    for a, b in zip(pts, pts[1:], strict=False):
        cumulative.append(cumulative[-1] + _haversine(a[:2], b[:2]))
    distance = float(props.get("summary", {}).get("distance") or cumulative[-1])
    ascent = props.get("ascent")
    descent = props.get("descent")
    alts = [p[2] for p in pts if p[2] is not None]
    if ascent is None and alts:
        ascent = sum(max(0.0, b - a) for a, b in zip(alts, alts[1:], strict=False))
        descent = sum(max(0.0, a - b) for a, b in zip(alts, alts[1:], strict=False))
    indices = range(len(pts))
    if len(pts) > PROFILE_POINTS:
        step = (len(pts) - 1) / (PROFILE_POINTS - 1)
        indices = sorted({round(i * step) for i in range(PROFILE_POINTS)})
    profile = [[round(cumulative[i]), round(pts[i][2], 1)] for i in indices if pts[i][2] is not None]
    extras = props.get("extras", {})
    geometry = _simplify([[round(p[0], 6), round(p[1], 6), round(p[2], 1) if p[2] is not None else None] for p in pts],
                         MAX_GEOMETRY)  # fmt: skip
    return {
        "geometry": geometry,
        "distance_m": round(distance),
        "ascent_m": round(ascent or 0),
        "descent_m": round(descent or 0),
        "profile": profile,
        "surfaces": _groups(extras.get("surface", {}).get("summary", []), SURFACE_GROUPS),
        "waytypes": _groups(extras.get("waytype", {}).get("summary", []), WAYTYPE_GROUPS),
        "max_altitude_m": round(max(alts)) if alts else None,
        "min_altitude_m": round(min(alts)) if alts else None,
    }


def easy_pace(session: Session, user_id: int) -> tuple[float, str]:
    """Ritmo fácil (s/km) del atleta por su VDOT, o el de por defecto si aún no hay datos."""
    from app.services import progress as prog
    from app.services.race_forecast import forecast, training_data
    from app.services.race_models import daniels_paces

    activities = prog.user_activities(session, user_id)
    f = forecast(10000, training_data(activities, date.today())) if activities else None
    if f and f.vdot_current:
        fast, slow = daniels_paces(f.vdot_current)["easy"]
        return (fast + slow) / 2, "tu ritmo fácil"
    return DEFAULT_EASY_PACE, "un ritmo fácil de 6:00/km"


def estimate_time_s(profile: list[list[float]], distance_m: float, mode: str, pace_s_km: float) -> int:
    """
    Tiempo estimado por tramos del perfil. A pie: ritmo × (1 + 0,033 por % de subida; −0,018 por % de bajada
    hasta −10 %), que se acerca a las tablas de ritmo ajustado por pendiente. En bici: velocidad de terreno,
    más 1 min por cada 10 m de subida en tramos empinados.
    """
    if mode in BIKE_SPEED_KMH:
        base = distance_m / (BIKE_SPEED_KMH[mode] / 3.6)
        climb = sum(max(0.0, b[1] - a[1]) for a, b in zip(profile, profile[1:], strict=False))
        return round(base + climb * 6)
    pace = pace_s_km * (TRAIL_FACTOR if mode == "trail" else 1.0)
    if len(profile) < 2:
        return round(distance_m / 1000 * pace)
    total = 0.0
    seen = 0.0
    for a, b in zip(profile, profile[1:], strict=False):
        d = b[0] - a[0]
        if d <= 0:
            continue
        grade = (b[1] - a[1]) / d * 100
        factor = 1 + 0.033 * grade if grade > 0 else 1 + 0.018 * max(grade, -10)
        total += d / 1000 * pace * max(factor, 0.8)
        seen += d
    if seen < distance_m:  # el perfil no llega al final exacto: el resto, en llano
        total += (distance_m - seen) / 1000 * pace
    return round(total)


def plan(session: Session, user_id: int, points: list[Waypoint], mode: str) -> dict:
    """Calcula la ruta (con caché) y le añade el tiempo estimado para esta persona."""
    if mode not in MODES:
        raise RouteError("Modo de ruta desconocido.")
    if len(points) < 2:
        raise RouteError("Marca al menos el inicio y el final.")
    if len(points) > MAX_POINTS:
        raise RouteError(f"Como mucho {MAX_POINTS} puntos por ruta.")
    for p in points:
        if not (-90 <= p.lat <= 90 and -180 <= p.lon <= 180):
            raise RouteError("Hay un punto con coordenadas no válidas.")
    key = _cache_key(points, mode)
    cache = _redis()
    result = None
    if cache:
        try:
            cached = cache.get(key)
            result = json.loads(cached) if cached else None
        except redis.RedisError:
            cache = None
    if result is None:
        body = {
            "coordinates": [[p.lon, p.lat] for p in points],
            "elevation": True,
            "instructions": False,
            "extra_info": ["surface", "waytype", "steepness"],
        }
        result = parse_ors(_ors_post(f"/v2/directions/{MODES[mode]}/geojson", body))
        if cache:
            with contextlib.suppress(redis.RedisError):
                cache.setex(key, CACHE_SECONDS, json.dumps(result))
    pace, basis = easy_pace(session, user_id)
    seconds = estimate_time_s(result["profile"], result["distance_m"], mode, pace)
    basis_text = "velocidad típica en bici" if mode in BIKE_SPEED_KMH else basis
    return {**result, "mode": mode, "estimated_s": seconds, "estimate_basis": basis_text}


def geocode(text: str) -> list[dict]:
    """Lugares que coinciden con el texto (para centrar el mapa)."""
    key = get_settings().ors_api_key
    if not key:
        raise RouteError("El planificador de rutas no está configurado (falta la clave de openrouteservice).")
    try:
        with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": "ktrain"}) as http:
            res = http.get(f"{ORS_URL}/geocode/autocomplete", params={"api_key": key, "text": text[:100]})
            res.raise_for_status()
    except httpx.HTTPError as exc:
        raise RouteError("No se pudo buscar el lugar. Prueba en un momento.") from exc
    out = []
    for f in res.json().get("features", [])[:6]:
        lon, lat = f["geometry"]["coordinates"][:2]
        out.append({"label": f.get("properties", {}).get("label", ""), "lat": lat, "lon": lon})
    return out


def to_gpx(name: str, geometry: list[list[float | None]]) -> bytes:
    """GPX con la traza y sus altitudes: lo importan Garmin Connect, COROS, Suunto, Polar…"""
    rows = "".join(
        f'<trkpt lat="{p[0]:.6f}" lon="{p[1]:.6f}">' + (f"<ele>{p[2]:.1f}</ele>" if p[2] is not None else "")
        + "</trkpt>"
        for p in geometry
    )  # fmt: skip
    safe = escape(name or "Ruta")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="KTrain" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<metadata><name>{safe}</name></metadata>"
        f"<trk><name>{safe}</name><trkseg>{rows}</trkseg></trk></gpx>"
    ).encode()


def summary(route: object) -> dict:
    """Resumen de una ruta guardada (para la sesión del plan y la IA)."""
    return {
        "id": route.id,
        "nombre": route.name,
        "modo": MODE_LABELS.get(route.mode, route.mode),
        "distancia_km": round(route.distance_m / 1000, 2),
        "desnivel_positivo_m": route.ascent_m,
        "desnivel_negativo_m": route.descent_m,
    }
