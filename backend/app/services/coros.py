"""
COROS Training Hub (API web no oficial, la misma que usa training.coros.com).

Referencias (código abierto, MIT): gandroz/coros_data_extractor y futoshita/Coros-Training-Hub-Exporter.
- Login: POST /account/login {account, accountType: 2, pwd: md5(contraseña)} → data.accessToken.
  Hay dos regiones (teameuapi para Europa, teamapi para el resto): se prueba una y luego la otra.
- Actividades: GET /activity/query?size&pageNumber&modeList= con cabecera `accessToken` → data.dataList
  (labelId, sportType…). FIT: POST /activity/detail/download?labelId&sportType&fileType=4 → data.fileUrl.
- Respuesta correcta: result == "0000". Puede cambiar sin aviso: todo falla de forma controlada.
"""

import hashlib
import logging
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from sqlmodel import Session, select

from app.core.crypto import decrypt_secret, encrypt_secret
from app.models import Activity, CorosCredential
from app.services.file_import import FileImportError, after_import, parse_fit, save_imported

logger = logging.getLogger(__name__)

BASES = ("https://teameuapi.coros.com", "https://teamapi.coros.com")
FIT_FILE_TYPE = 4
PAGE_SIZE = 20
MAX_PAGES = 5
OK = "0000"


class CorosError(RuntimeError):
    """COROS rechazó la petición (credenciales, token caducado, servicio caído…)."""


class CorosExpired(CorosError):
    """El token ya no vale: hay que volver a conectar."""


def _request(method: str, url: str, **kwargs) -> dict:
    """Petición a COROS (aislada para simularla en los tests)."""
    try:
        res = httpx.request(method, url, timeout=20, headers={"User-Agent": "Mozilla/5.0", **kwargs.pop("headers", {})},
                            **kwargs)  # fmt: skip
        res.raise_for_status()
        return res.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CorosError("No se pudo contactar con COROS. Inténtalo más tarde.") from exc


def _download(url: str) -> bytes:
    if urlparse(url).scheme != "https":
        raise CorosError("COROS devolvió un enlace de descarga no seguro.")
    try:
        res = httpx.get(url, timeout=60)
        res.raise_for_status()
        return res.content
    except httpx.HTTPError as exc:
        raise CorosError("No se pudo descargar el fichero de COROS.") from exc


def login(account: str, password: str) -> tuple[str, str]:
    """
    Entra en COROS y devuelve (token, url de su región). La contraseña no se guarda.

    Raises:
        CorosError: con el mensaje de COROS si las credenciales no valen.
    """
    body = {"account": account, "accountType": 2, "pwd": hashlib.md5(password.encode()).hexdigest()}  # noqa: S324
    message = "COROS no aceptó el email o la contraseña."
    for base in BASES:
        data = _request("POST", f"{base}/account/login", json=body)
        token = (data.get("data") or {}).get("accessToken")
        if data.get("result") == OK and token:
            return token, base
        message = data.get("message") or message
    raise CorosError(message)


def connect(session: Session, user_id: int, account: str, password: str) -> CorosCredential:
    token, base = login(account, password)
    cred = session.get(CorosCredential, user_id) or CorosCredential(user_id=user_id, account=account, token_enc="",
                                                                    base_url=base)  # fmt: skip
    cred.account, cred.token_enc, cred.base_url, cred.status, cred.last_error = (
        account,
        encrypt_secret(token),
        base,
        "ok",
        "",
    )
    session.add(cred)
    session.commit()
    return cred


def _call(cred: CorosCredential, method: str, path: str, **kwargs) -> dict:
    headers = {"accessToken": decrypt_secret(cred.token_enc)}
    data = _request(method, f"{cred.base_url}{path}", headers=headers, **kwargs)
    if data.get("result") != OK:
        msg = (data.get("message") or "").lower()
        if "token" in msg or "login" in msg or data.get("result") in ("1019", "1030"):
            raise CorosExpired("La sesión de COROS ha caducado: vuelve a conectar la cuenta.")
        raise CorosError(data.get("message") or "COROS devolvió un error.")
    return data.get("data") or {}


def list_activities(cred: CorosCredential, page: int) -> list[dict]:
    data = _call(cred, "GET", "/activity/query", params={"size": PAGE_SIZE, "pageNumber": page, "modeList": ""})
    return data.get("dataList") or []


def download_fit(cred: CorosCredential, label_id: str, sport_type: int) -> bytes:
    params = {"labelId": label_id, "sportType": sport_type, "fileType": FIT_FILE_TYPE}
    url = _call(cred, "POST", "/activity/detail/download", params=params).get("fileUrl")
    if not url:
        raise CorosError("COROS no ofrece el FIT de esta actividad.")
    return _download(url)


def _imported(session: Session, user_id: int, label: str) -> bool:
    return session.exec(select(Activity.id).where(
        Activity.user_id == user_id, Activity.source == "coros", Activity.external_id == label
    )).first() is not None  # fmt: skip


def sync(session: Session, user_id: int, max_new: int = 30) -> int:
    """
    Importa las actividades nuevas de COROS (de la más reciente hacia atrás, se para en la primera ya
    importada). Las que ya estén por otra fuente (p. ej. Garmin) no se duplican.

    Returns:
        Actividades nuevas.
    """
    cred = session.get(CorosCredential, user_id)
    if cred is None or cred.status == "expired":
        return 0
    created = 0
    try:
        for page in range(1, MAX_PAGES + 1):
            items = list_activities(cred, page)
            if not items:
                break
            stop = False
            for item in items:
                label = str(item.get("labelId") or "")
                if not label:
                    continue
                if _imported(session, user_id, label):
                    stop = True  # ya importada desde COROS: las anteriores también
                    break
                try:
                    act = parse_fit(download_fit(cred, label, int(item.get("sportType") or 0)))
                except (CorosError, FileImportError) as exc:
                    if isinstance(exc, CorosExpired):
                        raise
                    logger.warning("COROS: actividad sin FIT importable")
                    continue
                _, new = save_imported(session, user_id, act, "coros", label)
                if not new:
                    continue  # el mismo entreno ya estaba por otra fuente (p. ej. Garmin)
                created += 1
                if created >= max_new:
                    stop = True
                    break
            if stop:
                break
        cred.status, cred.last_error = "ok", ""
    except CorosExpired as exc:
        cred.status, cred.last_error = "expired", str(exc)[:255]
    except CorosError as exc:
        cred.status, cred.last_error = "error", str(exc)[:255]
    cred.last_sync_at = datetime.now(UTC)
    session.add(cred)
    session.commit()
    if created:
        after_import(session, user_id)
    return created
