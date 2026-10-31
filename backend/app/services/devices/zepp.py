"""
Amazfit (y Mi Band antiguas) por la nube de Zepp / Huami. No oficial: puede cambiar sin aviso.

Referencias (MIT): fjuliofontes/amazfit-mcp y rolandsz/Mi-Fit-and-Zepp-workout-exporter.
- Login (el de la web de Zepp, no cierra la sesión del móvil):
  1. POST api-user.huami.com/registrations/{email}/tokens → código `access` (en la redirección o el JSON).
  2. POST api-mifit.zepp.com/v2/client/login (grant_type=access_token) → login_token y user_id.
  3. GET  api-mifit.zepp.com/v1/client/app_tokens → app_token (lo único que guardamos, con el user_id).
- Entrenos: GET /v1/sport/run/history.json (cursor `trackid` = inicio en segundos; `count` = tamaño)
  y GET /v1/sport/run/detail.json. Cabecera `apptoken`. 401/403 = sesión caducada.
- El detalle trae el track como texto: `time` (segundos, en deltas), `longitude_latitude` (deltas ×1e8),
  `altitude` (cm) y `heart_rate` («dt,dFC», ambos en deltas).
"""

import json
import uuid
from datetime import UTC, datetime
from itertools import accumulate
from urllib.parse import parse_qs, quote, urlparse

import httpx

from app.services.devices import DeviceError, DeviceExpired, Provider, RemoteWorkout
from app.services.file_import import FileImportError, ImportedActivity, _summary_from_points

DATA = "https://api-mifit.zepp.com"
APP = "com.huami.webapp"
REDIRECT = "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html"
WEB_HEADERS = {"app_name": APP, "appname": APP, "appplatform": "web", "origin": "https://user.zepp.com",
               "referer": "https://user.zepp.com/", "user-agent": "Mozilla/5.0"}  # fmt: skip
DATA_HEADERS = {"appplatform": "android_phone", "appname": "com.huami.midong", "v": "2.0", "vn": "9.12.5",
                "cv": "151689_9.12.5", "channel": "a100900101016", "lang": "es_ES", "country": "ES",
                "user-agent": "Zepp/9.12.5 (Pixel 4; Android 12; Density/2.75)"}  # fmt: skip
PAGE = 50
MAX_PAGES = 6
NO_VALUE = -2000000
SENTINELS = {-1, -20000, -274, -361, NO_VALUE}

# Tipo de deporte de Zepp → nombres de la app (los de Garmin). Lo que no esté aquí queda como «other».
SPORTS = {
    1: "running", 6: "walking", 7: "trail_running", 8: "treadmill_running", 9: "cycling",
    10: "indoor_cycling", 11: "elliptical", 12: "elliptical", 13: "hiking", 14: "lap_swimming",
    15: "open_water_swimming", 16: "other", 22: "hiking", 23: "indoor_rowing", 24: "indoor_cardio",
    27: "yoga", 47: "mountain_biking", 49: "strength_training", 60: "yoga",
}  # fmt: skip


def _request(method: str, url: str, **kwargs) -> httpx.Response:
    """Petición a Zepp (aislada para simularla en los tests)."""
    try:
        return httpx.request(method, url, timeout=30, **kwargs)
    except httpx.HTTPError as exc:
        raise DeviceError("No se pudo contactar con Zepp. Inténtalo más tarde.") from exc


def _json(res: httpx.Response) -> dict:
    try:
        data = res.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def login(email: str, password: str, country: str = "ES") -> tuple[dict, str]:
    bad = DeviceError("Zepp no aceptó el email o la contraseña.")
    reg = _request("POST", f"https://api-user.huami.com/registrations/{quote(email, safe='')}/tokens", data={
        "client_id": "HuaMi", "country_code": country, "json_response": "true", "name": email,
        "password": password, "redirect_uri": REDIRECT, "state": "REDIRECTION", "token": "access",
    }, headers={**WEB_HEADERS, "x-request-id": str(uuid.uuid4())})  # fmt: skip
    code = parse_qs(urlparse(reg.headers.get("Location", "")).query).get("access", [None])[0]
    if not code and reg.status_code == 200:
        code = _json(reg).get("access") or _json(reg).get("code")
    if not code:
        raise bad
    res = _request("POST", f"{DATA}/v2/client/login", data={
        "allow_registration": "false", "app_name": APP, "app_version": "1.0.0", "code": code,
        "country_code": country, "device_id": f"web_{uuid.uuid4()}", "device_model": "web",
        "dn": "api-mifit.zepp.com,api-user.zepp.com,api-watch.zepp.com,auth.zepp.com",
        "grant_type": "access_token", "source": APP, "third_name": "huami",
    }, headers=WEB_HEADERS)  # fmt: skip
    info = _json(res).get("token_info") or {}
    if not info.get("login_token") or not info.get("user_id"):
        raise bad
    res = _request("GET", f"{DATA}/v1/client/app_tokens", params={
        "app_name": APP, "dn": "api-mifit.zepp.com,api-user.zepp.com,auth.zepp.com",
        "login_token": info["login_token"],
    }, headers=WEB_HEADERS)  # fmt: skip
    app_token = (_json(res).get("token_info") or {}).get("app_token")
    if not app_token:
        raise bad
    return {"app_token": app_token, "user_id": str(info["user_id"])}, email


def _get(sess: dict, path: str, params: dict) -> dict:
    headers = {**DATA_HEADERS, "apptoken": sess.get("app_token", ""), "x-request-id": str(uuid.uuid4())}
    res = _request("GET", f"{DATA}{path}", params={**params, "userid": sess.get("user_id", "")}, headers=headers)
    if res.status_code in (401, 403):
        raise DeviceExpired("La sesión de Zepp ha caducado: vuelve a conectar la cuenta.")
    if res.status_code >= 400:
        raise DeviceError("Zepp devolvió un error. Inténtalo más tarde.")
    return _json(res)


def _num(value, positive: bool = True) -> float | None:
    """Número de Zepp (a veces texto); sus valores «sin dato» (-1, -20000…) y, si `positive`, el 0 → None."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f in SENTINELS or (positive and f <= 0):
        return None
    return f


def _samples(raw: str | None) -> list[str]:
    return [s for s in (raw or "").split(";") if s]


def track_points(detail: dict, start: datetime) -> list[dict]:
    """Puntos con hora (y GPS, altitud y FC si los hay) del track codificado de Zepp."""
    times = list(accumulate(int(v) for v in _samples(detail.get("time"))))
    pairs = [v.split(",") for v in _samples(detail.get("longitude_latitude"))]
    lats = list(accumulate(int(p[0]) for p in pairs))
    lons = list(accumulate(int(p[1]) for p in pairs))
    alts = [int(v) for v in _samples(detail.get("altitude"))]
    hr_pairs = [v.split(",") for v in _samples(detail.get("heart_rate"))]
    hr_times = list(accumulate(int(p[0] or 1) for p in hr_pairs))
    hrs = list(accumulate(int(p[1]) for p in hr_pairs))

    def valid_hr(h: int | None) -> float | None:
        return float(h) if h and 30 <= h <= 240 else None

    def at(t: int) -> datetime:
        return datetime.fromtimestamp(start.timestamp() + t, UTC)

    if not times or len(lats) < len(times):
        return [{"time": at(t), "hr": valid_hr(h)} for t, h in zip(hr_times, hrs, strict=False)]
    points, j, last_hr = [], 0, None
    for i, t in enumerate(times):
        # La última FC medida hasta ese segundo (GPS y FC van a ritmos distintos).
        while j < len(hr_times) and hr_times[j] <= t:
            last_hr, j = hrs[j], j + 1
        alt = alts[i] if i < len(alts) else NO_VALUE
        points.append({
            "time": at(t), "lat": lats[i] / 1e8, "lon": lons[i] / 1e8,
            "ele": alt / 100 if alt != NO_VALUE else None, "hr": valid_hr(last_hr),
        })  # fmt: skip
    return points


def to_activity(summary: dict, detail: dict) -> ImportedActivity:
    """Entreno de Zepp → `ImportedActivity`: series del track y el resumen de Zepp (que manda en las cifras)."""
    start = datetime.fromtimestamp(int(summary["trackid"]), UTC)
    sport = SPORTS.get(int(_num(summary.get("type"), positive=False) or 0), "other")
    try:
        act = _summary_from_points(track_points(detail, start), sport)
    except FileImportError:
        act = ImportedActivity(sport=sport, start_time=start, duration_s=0)
    act.start_time = start
    act.duration_s = _num(summary.get("run_time")) or act.duration_s
    act.distance_m = _num(summary.get("highPrecisionDistance")) or _num(summary.get("dis")) or act.distance_m
    act.calories = _num(summary.get("calorie")) or act.calories
    act.avg_hr = _num(summary.get("avg_heart_rate")) or act.avg_hr
    act.max_hr = _num(summary.get("max_heart_rate")) or act.max_hr
    act.elevation_gain_m = _num(summary.get("altitude_ascend")) or act.elevation_gain_m
    if not act.duration_s:
        raise FileImportError("Entreno de Zepp sin duración.")
    return act


def _history(sess: dict, before: str | None) -> tuple[list[dict], str | None]:
    params = {"source": "run.mi.com", "count": str(PAGE)}
    if before:
        params["trackid"] = before
    body = _get(sess, "/v1/sport/run/history.json", params)
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    summary = data.get("summary") or []
    if isinstance(summary, str):  # algunas cuentas lo devuelven como JSON en texto
        try:
            summary = json.loads(summary)
        except ValueError:
            summary = []
    if isinstance(summary, dict):
        summary = summary.get("data") or []
    items = [w for w in summary if isinstance(w, dict) and w.get("trackid")]
    nxt = data.get("next")
    return items, None if nxt in (None, -1, "-1", 0, "0") else str(nxt)


def _detail(sess: dict, summary: dict) -> dict:
    params = {"trackid": str(summary["trackid"]), "source": summary.get("source") or "run.mi.com"}
    data = _get(sess, "/v1/sport/run/detail.json", params).get("data")
    return data if isinstance(data, dict) else {}


def workouts(sess: dict, since: datetime):
    cursor = None
    for _ in range(MAX_PAGES):
        items, cursor = _history(sess, cursor)
        for w in items:
            start = datetime.fromtimestamp(int(w["trackid"]), UTC)
            yield RemoteWorkout(str(w["trackid"]), start, lambda w=w: to_activity(w, _detail(sess, w)))
            if start < since:
                return
        if not cursor or not items:
            return


PROVIDER = Provider(key="zepp", label="Amazfit (Zepp)", login=login, workouts=workouts)
