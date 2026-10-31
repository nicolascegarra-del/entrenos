"""
Pulseras y relojes Xiaomi (Smart Band 8/9/10, Redmi Watch…) por la nube de Mi Fitness. No oficial y en beta.

Referencias (MIT): Jenwein/mifit y kevinkwee/Mi-Fitness-Sync. Xiaomi no deja entrar con contraseña desde
fuera: se entra con un **QR** que la persona aprueba en la app de Xiaomi del móvil.
1. GET account.xiaomi.com/longPolling/loginUrl?sid=miothealth&_json=true → `loginUrl`, `qr` (imagen) y `lp`.
2. GET `lp` (espera larga, hasta ~2 min, en una tarea): cuando se aprueba → userId, cUserId, ssecurity, nonce y
   `location` (la URL de STS). La respuesta empieza por «&&&START&&&».
3. GET `location` con clientSign = base64(SHA1("nonce=<nonce>&<ssecurity>")) → cookie `serviceToken`.
- Datos: hlth.io.mi.com (con prefijo de región: de, sg, us, ru…). Cada petición lleva un único parámetro
  `data` (JSON) firmado y cifrado con RC4 (clave = SHA256(ssecurity + nonce), descartando 1024 bytes) y la
  respuesta viene cifrada igual. Cookies: serviceToken, cUserId y userId.
- Entrenos: data/get_sport_records_by_time (paginado con `next_key`); cada fila trae `value` como JSON en
  texto (start_time, end_time, duration, distance, calories, avg_hrm, max_hrm, sport_type…). Solo resumen:
  el detalle segundo a segundo va en ficheros binarios cifrados aparte (aún no se importa).
- La sesión da acceso a toda la cuenta de Xiaomi: se guarda cifrada y nunca se registra en logs.
"""

import base64
import hashlib
import json
import os
import secrets
import struct
import time
from datetime import UTC, datetime
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlencode, urlparse

import httpx

from app.services.devices import DeviceError, DeviceExpired, Provider, RemoteWorkout
from app.services.file_import import ImportedActivity

ACCOUNT = "https://account.xiaomi.com"
SID = "miothealth"
HEALTH = "https://hlth.io.mi.com/app/v1/"
SAFE_PREFIX = "&&&START&&&"
DEFAULT_REGION = "de"  # Europa (España incluida); el resto: sg, us, ru, cn…
REGIONS = ("de", "sg", "us", "ru", "cn")
LONG_POLL_S = 120
PAGE = 50
MAX_PAGES = 10

SPORTS = {1: "running", 2: "walking", 3: "hiking", 4: "trail_running", 5: "treadmill_running", 6: "cycling",
          7: "indoor_cycling", 8: "elliptical", 9: "lap_swimming", 10: "open_water_swimming",
          300: "indoor_cardio", 308: "strength_training"}  # fmt: skip


# ─── Firma y cifrado (deben coincidir exactamente con la app) ─────────────────


class _Rc4:
    """RC4 con los primeros 1024 bytes del flujo descartados; el estado sigue entre llamadas."""

    def __init__(self, key: bytes) -> None:
        s, j = list(range(256)), 0
        for i in range(256):
            j = (j + s[i] + key[i % len(key)]) & 0xFF
            s[i], s[j] = s[j], s[i]
        self.s, self.i, self.j = s, 0, 0
        self.apply(bytes(1024))

    def apply(self, data: bytes) -> bytes:
        s, i, j, out = self.s, self.i, self.j, bytearray(len(data))
        for n, value in enumerate(data):
            i = (i + 1) & 0xFF
            j = (j + s[i]) & 0xFF
            s[i], s[j] = s[j], s[i]
            out[n] = value ^ s[(s[i] + s[j]) & 0xFF]
        self.i, self.j = i, j
        return bytes(out)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def new_nonce(now_ms: int | None = None) -> str:
    """8 bytes aleatorios + minutos desde 1970 (int32 big-endian), en base64."""
    minutes = (now_ms if now_ms is not None else int(time.time() * 1000)) // 60_000
    return _b64(os.urandom(8) + struct.pack(">i", minutes))


def signed_nonce(ssecurity: str, nonce: str) -> str:
    return _b64(hashlib.sha256(base64.b64decode(ssecurity) + base64.b64decode(nonce)).digest())


def signature(method: str, path: str, params: dict[str, str], snonce: str) -> str:
    parts = [method.upper(), urlparse(path).path, *(f"{k}={params[k]}" for k in sorted(params)), snonce]
    return _b64(hashlib.sha1("&".join(parts).encode()).digest())


def encrypt_params(path: str, params: dict[str, str], nonce: str, ssecurity: str) -> dict[str, str]:
    """Parámetros firmados (`rc4_hash__`), cifrados con un solo RC4 en orden de clave, y firmados de nuevo."""
    snonce = signed_nonce(ssecurity, nonce)
    plain = {k: v for k, v in params.items() if k and v}
    plain["rc4_hash__"] = signature("GET", path, plain, snonce)
    cipher = _Rc4(base64.b64decode(snonce))
    enc = {k: _b64(cipher.apply(v.encode())) for k, v in sorted(plain.items())}
    enc["signature"] = signature("GET", path, enc, snonce)
    enc["_nonce"] = nonce
    return enc


def decrypt_body(body: str, nonce: str, ssecurity: str) -> dict:
    raw = _Rc4(base64.b64decode(signed_nonce(ssecurity, nonce))).apply(base64.b64decode(body))
    data = json.loads(raw.decode())
    if not isinstance(data, dict):
        raise ValueError("respuesta no es un objeto")
    return data


def client_sign(nonce: str, ssecurity: str) -> str:
    return _b64(hashlib.sha1(f"nonce={nonce}&{ssecurity}".encode()).digest())


# ─── Login por QR ─────────────────────────────────────────────────────────────


def _request(method: str, url: str, **kwargs) -> httpx.Response:
    """Petición a Xiaomi (aislada para simularla en los tests)."""
    try:
        return httpx.request(method, url, timeout=kwargs.pop("timeout", 30), **kwargs)
    except httpx.TimeoutException as exc:
        raise DeviceError("El QR ha caducado sin aprobarse. Genera otro.") from exc
    except httpx.HTTPError as exc:
        raise DeviceError("No se pudo contactar con Xiaomi. Inténtalo más tarde.") from exc


def _account_json(res: httpx.Response) -> dict:
    if not 200 <= res.status_code < 300:
        raise DeviceError("Xiaomi rechazó la petición. Inténtalo más tarde.")
    body = res.text.strip().removeprefix(SAFE_PREFIX)
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise DeviceError("Xiaomi devolvió una respuesta que no se entiende.") from exc
    if not isinstance(data, dict) or str(data.get("code", "")) != "0":
        raise DeviceError("Xiaomi no aceptó el inicio de sesión. Genera otro QR.")
    return data


def _cookies(res: httpx.Response) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in res.headers.get_list("set-cookie"):
        try:
            jar = SimpleCookie()
            jar.load(raw)
        except CookieError:
            continue
        out.update({k: m.value for k, m in jar.items()})
    return out


def start_qr() -> dict:
    """
    Pide a Xiaomi un QR de inicio de sesión.

    Returns:
        {login_url, qr (URL de la imagen), lp (URL de espera), device_id}
    """
    device_id = secrets.token_hex(8).upper()
    url = f"{ACCOUNT}/longPolling/loginUrl?{urlencode({'sid': SID, '_json': 'true'})}"
    data = _account_json(_request("GET", url, cookies={"deviceId": device_id}))
    if not (data.get("loginUrl") and data.get("qr") and data.get("lp")):
        raise DeviceError("Xiaomi no devolvió el QR. Inténtalo más tarde.")
    qr = _qr_image(data["qr"], device_id)
    return {"login_url": data["loginUrl"], "qr": qr, "lp": data["lp"], "device_id": device_id}


def _qr_image(url: str, device_id: str) -> str:
    """
    La imagen del QR como `data:` URI: la web no carga imágenes de otros dominios (CSP), así que la
    descarga el servidor. Solo de un dominio de Xiaomi por https.
    """
    host = urlparse(url).hostname or ""
    if urlparse(url).scheme != "https" or not (host == "xiaomi.com" or host.endswith(".xiaomi.com")):
        raise DeviceError("Xiaomi devolvió un QR no seguro. Inténtalo más tarde.")
    res = _request("GET", url, cookies={"deviceId": device_id})
    kind = res.headers.get("content-type", "").split(";")[0].strip()
    if res.status_code != 200 or not kind.startswith("image/") or len(res.content) > 500_000:
        raise DeviceError("No se pudo descargar el QR de Xiaomi. Inténtalo más tarde.")
    return f"data:{kind};base64,{base64.b64encode(res.content).decode()}"


def finish_qr(pending: dict, region: str = DEFAULT_REGION) -> tuple[dict, str]:
    """
    Espera a que la persona apruebe el QR (bloquea hasta ~2 min: va en una tarea) y canjea el token.

    Returns:
        (sesión para guardar cifrada, cuenta a mostrar)
    """
    res = _request("GET", pending["lp"], cookies={"deviceId": pending["device_id"]}, timeout=LONG_POLL_S)
    data = _account_json(res)
    if int(data.get("securityStatus") or 0) != 0:
        raise DeviceError("Xiaomi pide una verificación de seguridad: entra una vez en su web y vuelve a probar.")
    cookies = _cookies(res)
    pragma: dict = {}
    if not (data.get("ssecurity") and data.get("nonce") is not None):
        try:
            pragma = json.loads(res.headers.get("extension-pragma") or "{}")
        except ValueError:
            pragma = {}
    user_id = str(data.get("userId") or cookies.get("userId") or "")
    c_user_id = str(data.get("cUserId") or cookies.get("cUserId") or "")
    ssecurity = str(data.get("ssecurity") or pragma.get("ssecurity") or "")
    nonce = str(data.get("nonce") if data.get("nonce") is not None else pragma.get("nonce", ""))
    location = str(data.get("location") or "")
    if not (user_id and c_user_id and ssecurity and nonce and location):
        raise DeviceError("Xiaomi no completó el inicio de sesión. Genera otro QR.")
    parsed = urlparse(location)
    if parsed.scheme != "https" or not parsed.hostname:
        raise DeviceError("Xiaomi devolvió un enlace no seguro.")
    # La URL de STS ya trae su propia firma: se le añaden los parámetros sin volver a codificar los suyos
    # (con `params=`, httpx reescribe la query y Xiaomi responde 400 sin token).
    extra = urlencode({"clientSign": client_sign(nonce, ssecurity), "_userIdNeedEncrypt": "true"})
    sts_url = f"{location}{'&' if '?' in location else '?'}{extra}"
    sts = _request("GET", httpx.URL(sts_url), follow_redirects=False)
    if sts.status_code not in (200, 302):
        raise DeviceError("Xiaomi no completó el inicio de sesión. Genera otro QR.")
    sts_cookies = _cookies(sts)
    token = sts_cookies.get(f"{SID}_serviceToken") or sts_cookies.get("serviceToken")
    if not token:
        raise DeviceError("Xiaomi no completó el inicio de sesión. Genera otro QR.")
    region = region if region in REGIONS else DEFAULT_REGION
    sess = {"service_token": token, "ssecurity": ssecurity, "user_id": user_id, "c_user_id": c_user_id,
            "region": region}  # fmt: skip
    return sess, f"Cuenta Xiaomi {user_id}"


# ─── Datos ────────────────────────────────────────────────────────────────────


def _host(url: str, region: str) -> str:
    return url if region == "cn" else url.replace("://", f"://{region}.", 1)


def call(sess: dict, endpoint: str, payload: dict) -> dict:
    """Petición firmada y cifrada a Mi Fitness; devuelve el JSON descifrado (con `code == 0`)."""
    url = HEALTH + endpoint
    nonce = new_nonce()
    params = encrypt_params(urlparse(url).path, {"data": json.dumps(payload, separators=(",", ":"))}, nonce,
                            sess["ssecurity"])  # fmt: skip
    cookie = f"serviceToken={sess['service_token']}; cUserId={sess['c_user_id']}; userId={sess['user_id']}"
    res = _request("GET", _host(url, sess.get("region", DEFAULT_REGION)), params=params,
                   headers={"Cookie": cookie, "region_tag": sess.get("region", DEFAULT_REGION)})  # fmt: skip
    if res.status_code == 401:
        raise DeviceExpired("La sesión de Xiaomi ha caducado: vuelve a conectar escaneando el QR.")
    if not 200 <= res.status_code < 300:
        raise DeviceError("Xiaomi devolvió un error. Inténtalo más tarde.")
    try:
        data = decrypt_body(res.text, nonce, sess["ssecurity"])
    except (ValueError, UnicodeDecodeError) as exc:
        raise DeviceError("Xiaomi devolvió una respuesta que no se entiende.") from exc
    if data.get("code") != 0:
        raise DeviceError("Xiaomi devolvió un error. Inténtalo más tarde.")
    return data


def _pos(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def to_activity(value: dict) -> ImportedActivity:
    """Fila de entreno de Mi Fitness → `ImportedActivity` (solo resumen)."""
    start = datetime.fromtimestamp(int(value["start_time"]), UTC)
    end = _pos(value.get("end_time"))
    duration = _pos(value.get("duration")) or ((end - start.timestamp()) if end else None)
    if not duration:
        raise ValueError("entreno sin duración")
    tz = value.get("timezone")
    offset = int(tz) * 900 if isinstance(tz, int | float) else None
    return ImportedActivity(
        sport=SPORTS.get(int(value.get("sport_type") or 0), "other"),
        start_time=start,
        duration_s=duration,
        distance_m=_pos(value.get("distance")),
        calories=_pos(value.get("calories")),
        avg_hr=_pos(value.get("avg_hrm")),
        max_hr=_pos(value.get("max_hrm")),
        timezone=(
            f"{'+' if offset >= 0 else '-'}{abs(offset) // 3600:02d}:{abs(offset) % 3600 // 60:02d}"
            if offset is not None
            else None
        ),  # fmt: skip
    )


def workouts(sess: dict, since: datetime):
    request = {"start_time": int(since.timestamp()) - 1, "end_time": int(time.time()), "reverse": True,
               "limit": PAGE}  # fmt: skip
    rows: list[dict] = []
    for _ in range(MAX_PAGES):
        data = call(sess, "data/get_sport_records_by_time", request)
        body = data.get("result") if isinstance(data.get("result"), dict) else data
        rows.extend(r for r in body.get("sport_records") or [] if isinstance(r, dict) and not r.get("deleted"))
        nxt = body.get("next_key")
        if not body.get("has_more") or not nxt or nxt == request.get("next_key"):
            break
        request = {**request, "next_key": nxt}
    for row in rows:
        try:
            value = json.loads(row["value"]) if isinstance(row.get("value"), str) else row.get("value")
        except ValueError:
            continue
        if not isinstance(value, dict) or not _pos(value.get("start_time")):
            continue
        start = datetime.fromtimestamp(int(value["start_time"]), UTC)
        key = f"{value['start_time']}-{value.get('sport_type', '')}"
        yield RemoteWorkout(key, start, lambda value=value: to_activity(value))


PROVIDER = Provider(key="xiaomi", label="Xiaomi (Mi Fitness)", login=None, workouts=workouts)
