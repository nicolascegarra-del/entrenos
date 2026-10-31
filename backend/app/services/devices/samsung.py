"""
Samsung Health (relojes Galaxy Watch y el móvil) por la nube privada de Samsung. No oficial y en beta.

Referencia (MIT): charlesbel/samsung-re-health. La contraseña nunca pasa por aquí: se entra en la propia
web de Samsung y al terminar Samsung redirige a un enlace `ms-app://…` que el navegador no sabe abrir; la
persona lo copia (consola del navegador, F12) y lo pega en la app.
1. GET account.samsung.com/accounts/ANDROIDSDK/getEntryPoint → clave pública RSA, `chkDoNum` y signInURI.
   Los parámetros de login (PKCE, estado, dispositivo) van cifrados: AES-CBC con una clave PBKDF2 y esa
   clave cifrada con RSA (PKCS#1 v1.5).
2. La redirección trae `state`, `code`, `auth_server_url` y `retValue` cifrados con AES-ECB: la clave del
   `state` es nuestro estado; la del resto, el `state` descifrado.
3. POST {auth_server}/auth/oauth2/authenticate → `userauth_token` (token maestro; es lo que guardamos).
4. Cada sincronización: GET /auth/oauth2/v2/authorize + POST /auth/oauth2/token (cliente de Samsung Health)
   → token de Health; POST play.samsungcloud.com/identity/v1/register (una vez) y /identity/v1/tokens →
   token de la nube; GET api.samsungcloud.com/data/v3/com.samsung.health.exercise/documents.
- Los documentos con cifrado de extremo a extremo (`needToDecrypt`) no se pueden leer: se saltan.
"""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
from datetime import UTC, datetime

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_der_public_key

from app.services.devices import DeviceError, DeviceExpired, Provider, RemoteWorkout
from app.services.file_import import ImportedActivity

ENTRY_POINT = "https://account.samsung.com/accounts/ANDROIDSDK/getEntryPoint"
ACCOUNT_CLIENT_ID = "yfrtglt53o"
HEALTH_CLIENT_ID = "1y90e30264"
REDIRECT_URI = "ms-app://s-1-15-2-4027708247-2189610-1983755848-2937435718-1578786913-2158692839-1974417358"
PLAY = "https://play.samsungcloud.com"
DATA = "https://api.samsungcloud.com"
APP_VERSION = "7.00.6.003"
SCSP_VERSION = "1.0.1105"
EXERCISE = "com.samsung.health.exercise"
EXERCISE_REVISION = 36
PAGE = 200
MAX_PAGES = 10
PENDING_MAX_AGE_S = 15 * 60
USER_AGENT = (
    f"SM-GENERIC; ANDROID; com.sec.android.app.shealth={APP_VERSION}; android sdk=34, sw=14; core={SCSP_VERSION}"
)

# Tipo de ejercicio de Samsung Health → nombres de la app (los de Garmin). Lo demás, «other».
SPORTS = {1001: "walking", 1002: "running", 11007: "cycling", 13001: "hiking", 14001: "lap_swimming",
          15003: "indoor_cycling", 15004: "elliptical", 15005: "indoor_rowing", 10007: "strength_training"}  # fmt: skip


# ─── Cifrado del login ───────────────────────────────────────────────────────


def _urlsafe(n: int) -> str:
    return base64.urlsafe_b64encode(os.urandom(n)).rstrip(b"=").decode()


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def encrypt_svc_param(payload: dict, chk_do_num: int, public_key_b64: str) -> str:
    """Parámetros del login cifrados como los manda la app de Samsung (AES-CBC + clave con RSA)."""
    if chk_do_num < 1:
        raise ValueError("chkDoNum no válido")
    chk = str(chk_do_num)
    derived = hashlib.pbkdf2_hmac(
        "sha256", base64.b64encode(hashlib.sha256(chk.encode()).digest()), os.urandom(16), chk_do_num, dklen=16
    )
    key = load_der_public_key(base64.b64decode(public_key_b64, validate=True))
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("la clave de Samsung no es RSA")
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(json.dumps(payload, separators=(",", ":")).encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(derived), modes.CBC(iv)).encryptor()
    envelope = {
        "chkDoNum": chk,
        "svcEncParam": base64.b64encode(enc.update(padded) + enc.finalize()).decode(),
        "svcEncKY": base64.b64encode(key.encrypt(base64.b64encode(derived), asym_padding.PKCS1v15())).decode(),
        "svcEncIV": iv.hex(),
    }
    return urllib.parse.quote(base64.b64encode(json.dumps(envelope).encode()).decode(), safe="")


def decrypt_value(value: str, key: str) -> str:
    """Campo de la redirección (hex, AES-ECB con la clave rellenada a 16 bytes)."""
    k = key.encode()[:16].ljust(16, b"\0")
    dec = Cipher(algorithms.AES(k), modes.ECB()).decryptor()  # noqa: S305 — así lo cifra Samsung
    padded = dec.update(bytes.fromhex(value)) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode()


def _trusted_auth_server(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or "").lower()
    ok = host in ("account.samsung.com", "samsungosp.com") or host.endswith(".samsungosp.com")
    if parsed.scheme != "https" or not ok or parsed.path not in ("", "/") or parsed.query or parsed.port not in (
        None, 443,
    ):  # fmt: skip
        raise DeviceError("Samsung devolvió un servidor de acceso no fiable.")
    return f"https://{host}"


# ─── Peticiones ──────────────────────────────────────────────────────────────


def _request(method: str, url: str, **kwargs) -> httpx.Response:
    """Petición a Samsung (aislada para simularla en los tests). Nunca sigue redirecciones."""
    try:
        return httpx.request(method, url, timeout=30, follow_redirects=False, **kwargs)
    except httpx.HTTPError as exc:
        raise DeviceError("No se pudo contactar con Samsung. Inténtalo más tarde.") from exc


def _json(res: httpx.Response, what: str) -> dict:
    if res.status_code in (401, 403):
        raise DeviceExpired("La sesión de Samsung ha caducado: vuelve a conectar la cuenta.")
    if res.status_code != 200:
        raise DeviceError(f"Samsung rechazó la petición ({what}). Inténtalo más tarde.")
    try:
        data = res.json()
    except ValueError as exc:
        raise DeviceError("Samsung devolvió una respuesta que no se entiende.") from exc
    if not isinstance(data, dict):
        raise DeviceError("Samsung devolvió una respuesta que no se entiende.")
    return data


# ─── Login ───────────────────────────────────────────────────────────────────


def start_login(country: str = "es", locale: str = "es-ES") -> tuple[str, dict]:
    """
    Prepara el inicio de sesión en la web de Samsung.

    Returns:
        (URL de la web de Samsung a abrir, datos pendientes a guardar hasta que vuelva la redirección)
    """
    entry = _json(_request("GET", ENTRY_POINT), "entrada")
    sign_in = urllib.parse.urlsplit(str(entry.get("signInURI") or ""))
    if sign_in.scheme != "https" or sign_in.hostname != "account.samsung.com" or not sign_in.path.startswith(
        "/accounts/"
    ):  # fmt: skip
        raise DeviceError("Samsung devolvió una página de acceso no fiable.")
    device_id, state, verifier = secrets.token_hex(16), _urlsafe(15)[:20], _urlsafe(32)[:43]
    payload = {
        "clientId": ACCOUNT_CLIENT_ID, "code_challenge": _challenge(verifier), "code_challenge_method": "S256",
        "competitorDeviceYNFlag": "Y", "countryCode": country.lower(), "deviceInfo": "Google|com.android.chrome",
        "deviceModelID": "Pixel 8 Pro", "deviceName": "Google Pixel 8 Pro", "deviceOSVersion": "35",
        "devicePhysicalAddressText": f"ANID:{device_id}", "deviceType": "APP", "deviceUniqueID": device_id,
        "redirect_uri": REDIRECT_URI, "replaceableClientConnectYN": "N", "replaceableClientId": "",
        "replaceableDevicePhysicalAddressText": "", "responseEncryptionType": "1",
        "responseEncryptionYNFlag": "Y", "scope": "", "state": state, "svcIptLgnID": "", "iosYNFlag": "Y",
    }  # fmt: skip
    try:
        svc = encrypt_svc_param(payload, int(entry["chkDoNum"]), str(entry["pkiPublicKey"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise DeviceError("Samsung devolvió una clave no válida. Inténtalo más tarde.") from exc
    url = f"https://account.samsung.com{sign_in.path}?locale={urllib.parse.quote(locale)}&svcParam={svc}&mode=C"
    pending = {"state": state, "verifier": verifier, "device_id": device_id, "created_at": int(time.time())}
    return url, pending


def finish_login(pending: dict, redirect: str) -> tuple[dict, str]:
    """
    Canjea la URL `ms-app://…` que devuelve Samsung por el token maestro.

    Returns:
        (sesión para guardar cifrada, cuenta a mostrar)
    """
    if time.time() - float(pending.get("created_at") or 0) > PENDING_MAX_AGE_S:
        raise DeviceError("Han pasado más de 15 minutos: vuelve a empezar el inicio de sesión.")
    redirect = redirect.strip()
    if not redirect.startswith(REDIRECT_URI):
        raise DeviceError("Ese enlace no es el de Samsung: copia el que empieza por «ms-app://».")
    parts = urllib.parse.urlsplit(redirect)
    params = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
    params.update(urllib.parse.parse_qs(parts.fragment, keep_blank_values=True))

    def one(name: str) -> str:
        values = params.get(name) or [""]
        if not values[0]:
            raise DeviceError("Al enlace le falta información: cópialo entero.")
        return values[0]

    try:
        key = decrypt_value(one("state"), pending["state"])
        auth_server = decrypt_value(one("auth_server_url"), key)
        code = decrypt_value(one("code"), key)
        login_id = decrypt_value(one("retValue"), key)
    except DeviceError:
        raise
    except (ValueError, KeyError) as exc:
        raise DeviceError("El enlace no corresponde a este inicio de sesión: vuelve a empezar.") from exc
    server = _trusted_auth_server(auth_server)
    data = _json(_request("POST", f"{server}/auth/oauth2/authenticate", data={
        "grant_type": "authorization_code", "serviceType": "M", "client_id": ACCOUNT_CLIENT_ID, "code": code,
        "code_verifier": pending["verifier"], "username": login_id, "physical_address_text": pending["device_id"],
    }), "acceso")  # fmt: skip
    token = data.get("userauth_token") or data.get("userAuthToken")
    user_id = data.get("userId") or data.get("user_id")
    if not token or not user_id:
        raise DeviceError("Samsung no completó el inicio de sesión. Vuelve a empezar.")
    sess = {"auth_server": server, "master_token": token, "login_id": login_id, "user_id": str(user_id),
            "device_id": pending["device_id"], "cdid": secrets.token_hex(32)}  # fmt: skip
    return sess, login_id


# ─── Datos ───────────────────────────────────────────────────────────────────


def _health_token(sess: dict) -> str:
    verifier = secrets.token_urlsafe(64)
    params = {
        "response_type": "code", "serviceType": "M", "client_id": HEALTH_CLIENT_ID,
        "code_challenge": _challenge(verifier), "code_challenge_method": "S256", "childAccountSupported": "Y",
        "userauth_token": sess["master_token"], "physical_address_text": sess["device_id"],
        "login_id": sess["login_id"],
    }  # fmt: skip
    server = _trusted_auth_server(sess["auth_server"])
    auth = _json(_request("GET", f"{server}/auth/oauth2/v2/authorize", params=params,
                          headers={"Accept": "application/json"}), "autorización")  # fmt: skip
    code = auth.get("code")
    if not code:
        raise DeviceExpired("La sesión de Samsung ha caducado: vuelve a conectar la cuenta.")
    tok = _json(_request("POST", f"{server}/auth/oauth2/token", headers={"Accept": "application/json"}, data={
        "grant_type": "authorization_code", "code": code, "client_id": HEALTH_CLIENT_ID, "client_secret": "",
        "physical_address_text": sess["device_id"], "code_verifier": verifier,
    }), "token")  # fmt: skip
    if not tok.get("access_token"):
        raise DeviceError("Samsung no dio acceso a Samsung Health.")
    return str(tok["access_token"])


def _cloud_token(sess: dict, health_token: str) -> str:
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json",
               "x-sc-app-id": HEALTH_CLIENT_ID, "x-sc-cdid": sess["cdid"], "x-sc-access-token": health_token,
               "x-sc-uid": sess["user_id"]}  # fmt: skip
    if not sess.get("registration_id"):
        reg = _json(_request("POST", f"{PLAY}/identity/v1/register", headers=headers, json={
            "app": {"version": APP_VERSION},
            "device": {"osType": "android", "osVersion": "34", "platformVersion": "6.0.0", "type": "phone",
                       "countryCode": "ESP", "modelName": "SM-GENERIC", "alias": "KTrain", "osUserId": "0"},
        }), "registro")  # fmt: skip
        sess["registration_id"] = str(reg.get("registrationId") or "")
    tok = _json(_request("POST", f"{PLAY}/identity/v1/tokens", headers={**headers, "x-sc-app-version": APP_VERSION}),
                "nube")  # fmt: skip
    if not tok.get("accessToken"):
        raise DeviceError("Samsung no dio acceso a su nube.")
    return f"{tok.get('tokenType') or 'Bearer'} {tok['accessToken']}"


def to_activity(data: dict) -> ImportedActivity:
    """Documento de ejercicio de Samsung Health → `ImportedActivity` (solo resumen; tiempos en ms)."""
    start = datetime.fromtimestamp(int(data["start_time"]) / 1000, UTC)
    duration = float(data.get("duration") or 0) / 1000 or (float(data.get("end_time") or 0) / 1000 - start.timestamp())
    if duration <= 0:
        raise ValueError("entreno sin duración")
    offset = data.get("time_offset")
    tz = None
    if isinstance(offset, int | float):
        mins = int(offset) // 60000
        tz = f"{'+' if mins >= 0 else '-'}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}"

    def pos(key: str) -> float | None:
        v = data.get(key)
        return float(v) if isinstance(v, int | float) and v > 0 else None

    return ImportedActivity(
        sport=SPORTS.get(int(data.get("exercise_type") or 0), "other"), start_time=start, duration_s=duration,
        distance_m=pos("distance"), calories=pos("calorie"), avg_hr=pos("mean_heart_rate"),
        max_hr=pos("max_heart_rate"), elevation_gain_m=pos("altitude_gain"), timezone=tz,
    )  # fmt: skip


def workouts(sess: dict, since: datetime):
    cloud = _cloud_token(sess, _health_token(sess))
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT,
               "authorization": cloud, "x-sc-e2ee-state": "OFF"}  # fmt: skip
    docs: list[dict] = []
    encrypted = 0
    token = None
    for _ in range(MAX_PAGES):
        params = {"schemaRevision": str(EXERCISE_REVISION), "limit": str(PAGE),
                  "start_time": str(int(since.timestamp() * 1000))}  # fmt: skip
        if token:
            params["pageToken"] = token
        page = _json(_request("GET", f"{DATA}/data/v3/{EXERCISE}/documents", params=params, headers=headers),
                     "entrenos")  # fmt: skip
        for env in page.get("documents") or []:
            if not isinstance(env, dict):
                continue
            if env.get("needToDecrypt") is True:
                encrypted += 1
                continue
            if isinstance(env.get("data"), dict) and env["data"].get("start_time"):
                docs.append(env["data"])
        nxt = page.get("nextPageToken")
        if not nxt or nxt == token:
            break
        token = nxt
    if encrypted and not docs:
        raise DeviceError(
            "Tus entrenos de Samsung Health están cifrados de extremo a extremo y no se pueden leer desde fuera."
        )
    docs.sort(key=lambda d: int(d["start_time"]), reverse=True)
    for d in docs:
        uid = str(d.get("datauuid") or d.get("uuid") or d["start_time"])
        yield RemoteWorkout(uid, datetime.fromtimestamp(int(d["start_time"]) / 1000, UTC),
                            lambda d=d: to_activity(d))  # fmt: skip


PROVIDER = Provider(key="samsung", label="Samsung Health", login=None, workouts=workouts)
