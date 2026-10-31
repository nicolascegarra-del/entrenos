"""
Suunto (API privada de la app Suunto, la de Sports Tracker). No oficial: puede cambiar sin aviso.

Referencias (MIT): tajchert/suuntool (Go) y MichalZaniewicz/ha-suunto (su port a Python).
- Login: POST {API}login2 (formulario) con l=email, p=contraseña, totp, timestamp, salt y signature.
  `signature` = base64url(SHA-256("POST&login2&l=…&p=…&totp=…&secret=" + clave de la app)); el TOTP sale de
  una clave maestra de la app derivada con PBKDF2 por email. Devuelve `sessionkey` (lo único que guardamos).
- Datos: cabecera `STTAuthorization: <sessionkey>`. Entrenos: GET workouts?since&limit&offset (sobre
  {error, payload}); FIT: GET workout/exportFit/{key}. 401/403 = sesión caducada.
- Suunto manda un email en cada login: por eso se guarda la sesión y no se vuelve a entrar.
"""

import base64
import hashlib
import hmac
import os
import struct
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx

from app.services.devices import DeviceError, DeviceExpired, Provider, RemoteWorkout
from app.services.file_import import parse_fit

API = "https://api.sports-tracker.com/apiserver/v1/"
PAGE = 50
MAX_PAGES = 6

# Material de la app Android (com.stt.android.suunto 6.8.13), el mismo que usan los proyectos de referencia.
PACKAGE = "com.stt.android.suunto"
USER_AGENT = f"{PACKAGE}/6008013"
_LOGIN_KEY = (
    "FBkubDYmN28bWVQLLTsWFxcmaRBfN2AqIBc/IRAoNgshbxgnOGUVGlU3LC0xL0AuXXXXMXYRWQ4zIi0PWz4hekc1QGNTPlciNhEKV1teYSIkDGYY"
)
_TOTP_KEY = (
    "FBkubDYmN28bWVQLLTsWWhI+NAtILCNlPQc5YBgiMRYjKA99Jj4HHFIqLmomOFttBQchNzcZU0QrODcDWz4hekc1QGNTPlciNhEKGl5GPDkzFyVX"
)
_TOTP_XOR = "Bh8nsTyCeC0Ql2drMen78awk84AE3ZxW"


def _rune_len(raw: bytes, i: int) -> int:
    """Bytes de la secuencia UTF-8 válida que empieza en `i` (0 si no lo es), como `utf8.DecodeRune` de Go."""
    b0 = raw[i]
    if b0 < 0x80:
        return 1
    if 0xC2 <= b0 <= 0xDF:
        size, lo, hi = 2, 0x80, 0xBF
    elif 0xE0 <= b0 <= 0xEF:
        size, lo, hi = 3, 0xA0 if b0 == 0xE0 else 0x80, 0x9F if b0 == 0xED else 0xBF
    elif 0xF0 <= b0 <= 0xF4:
        size, lo, hi = 4, 0x90 if b0 == 0xF0 else 0x80, 0x8F if b0 == 0xF4 else 0xBF
    else:
        return 0
    if i + size > len(raw) or not lo <= raw[i + 1] <= hi:
        return 0
    return size if all(0x80 <= c <= 0xBF for c in raw[i + 2 : i + size]) else 0


def _utf8_replace(raw: bytes) -> bytes:
    """
    Como Java `new String(bytes, UTF-8).getBytes(UTF-8)`: CADA byte inválido pasa a U+FFFD por separado
    (`bytes.decode(errors="replace")` agrupa secuencias truncadas y daría otra clave).
    """
    out, i = bytearray(), 0
    while i < len(raw):
        n = _rune_len(raw, i)
        out += raw[i : i + n] if n else b"\xef\xbf\xbd"
        i += n or 1
    return bytes(out)


def _secret(b64: str, xor_key: str) -> bytes:
    """Clave de la app: base64 → UTF-8 «reparado» → XOR con la clave → UTF-8 «reparado»."""
    mid = _utf8_replace(base64.b64decode(b64))
    k = xor_key.encode()
    return _utf8_replace(bytes(b ^ k[i % len(k)] for i, b in enumerate(mid)))


def sign(path: str, params: list[tuple[str, str]]) -> str:
    buf = b"POST&" + path.encode() + b"".join(b"&" + k.encode() + b"=" + v.encode() for k, v in params)
    digest = hashlib.sha256(buf + b"&secret=" + _secret(_LOGIN_KEY, PACKAGE)).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def totp(email: str, now_ms: int | None = None) -> str:
    """TOTP de 6 cifras (RFC 6238, pasos de 30 s) con la clave PBKDF2(maestra, email)."""
    master = _secret(_TOTP_KEY, _TOTP_XOR).decode()
    key = hashlib.pbkdf2_hmac("sha1", bytes(ord(c) & 0xFF for c in master), email.encode(), 100, 32)
    counter = (now_ms if now_ms is not None else int(time.time() * 1000)) // 30000
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = int.from_bytes(mac[off : off + 4], "big") & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def _request(method: str, url: str, **kwargs) -> httpx.Response:
    """Petición a Suunto (aislada para simularla en los tests)."""
    try:
        return httpx.request(method, url, timeout=45, **kwargs)
    except httpx.HTTPError as exc:
        raise DeviceError("No se pudo contactar con Suunto. Inténtalo más tarde.") from exc


def login(email: str, password: str) -> tuple[dict, str]:
    code = totp(email)
    form = {
        "l": email,
        "p": password,
        "totp": code,
        "timestamp": str(int(time.time() * 1000)),
        "salt": base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode(),
        "signature": sign("login2", [("l", email), ("p", password), ("totp", code)]),
    }
    res = _request("POST", f"{API}login2", content=urlencode(form), headers={
        "User-Agent": USER_AGENT, "Accept-Language": "en",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "x-login-email-verification-enabled": "true",
    })  # fmt: skip
    if res.status_code in (401, 403):
        raise DeviceError("Suunto no aceptó el email o la contraseña.")
    try:
        if res.status_code >= 400:
            raise ValueError(res.status_code)
        data = res.json()
    except ValueError as exc:
        raise DeviceError("Suunto respondió con un error. Inténtalo más tarde.") from exc
    key = data.get("sessionkey")
    if not key:
        raise DeviceError("Suunto no aceptó el email o la contraseña.")
    return {"session_key": key}, data.get("username") or email


def _get(sess: dict, path: str) -> httpx.Response:
    res = _request("GET", f"{API}{path}", headers={
        "User-Agent": USER_AGENT, "Accept-Language": "en", "STTAuthorization": sess.get("session_key", ""),
    })  # fmt: skip
    if res.status_code in (401, 403):
        raise DeviceExpired("La sesión de Suunto ha caducado: vuelve a conectar la cuenta.")
    if res.status_code >= 400:
        raise DeviceError("Suunto devolvió un error. Inténtalo más tarde.")
    return res


def workouts(sess: dict, since: datetime):
    since_ms = int(since.timestamp() * 1000)
    items: list[dict] = []
    for page in range(MAX_PAGES):
        try:
            body = _get(sess, f"workouts?since={since_ms}&limit={PAGE}&offset={page * PAGE}").json()
        except ValueError as exc:
            raise DeviceError("Suunto devolvió una respuesta que no se entiende.") from exc
        if isinstance(body, dict) and body.get("error"):
            raise DeviceError("Suunto devolvió un error. Inténtalo más tarde.")
        chunk = body.get("payload") if isinstance(body, dict) else None
        chunk = chunk if isinstance(chunk, list) else []
        items.extend(w for w in chunk if isinstance(w, dict) and w.get("key") and w.get("startTime"))
        if len(chunk) < PAGE:
            break
    items.sort(key=lambda w: w["startTime"], reverse=True)
    for w in items:
        key = str(w["key"])
        yield RemoteWorkout(
            external_id=key,
            start_time=datetime.fromtimestamp(int(w["startTime"]) / 1000, UTC),
            fetch=lambda key=key: parse_fit(_get(sess, f"workout/exportFit/{key}").content),
        )


PROVIDER = Provider(key="suunto", label="Suunto", login=login, workouts=workouts)
