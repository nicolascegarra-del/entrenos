"""
Traer las actividades de COROS por la conexión oficial (MCP con OAuth).

`querySportRecords` devuelve texto pensado para un asistente; de él solo se sacan el LabelId y el
SportType de cada actividad. Luego se descarga el .FIT de cada una nueva (`downloadActivityFitFiles` con
su LabelId; por rango de fechas COROS lo bloquea), que trae todo (deporte, ruta, pulso, potencia,
vueltas) y se lee con el mismo lector que cualquier FIT.

COROS limita a 50 ficheros al día: solo se descargan las que faltan, como mucho 10 por pasada, cada 6 h.
Lo que ya estaba (de esta conexión, de la antigua o de otro reloj) no se duplica (`save_imported`).
"""

import base64
import logging
import re
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlmodel import Session

from app.models import CorosOAuth
from app.services.coros_oauth import CorosMcp, CorosOAuthError
from app.services.file_import import FileImportError, after_import, parse_fit, save_imported

logger = logging.getLogger(__name__)

DAYS_BACK = 3  # cada pasada mira los últimos días
FIRST_SYNC_DAYS = 60  # al conectar, el historial reciente
MAX_FILES = 10
_URL = re.compile(r"https://[^\s\"'<>)]+")
BLOCKED = "COROS no ha dejado descargar tus actividades por la conexión oficial. Inténtalo más tarde."


def fit_blobs(result: dict) -> list[bytes]:
    """Ficheros FIT de una respuesta MCP: recursos embebidos (base64) o enlaces de descarga."""
    files: list[bytes] = []
    urls: list[str] = []
    for item in result.get("content", []) or []:
        kind = item.get("type")
        resource = item.get("resource") or {}
        if kind == "resource" and resource.get("blob"):
            files.append(base64.b64decode(resource["blob"]))
        elif kind in ("blob", "binary") and item.get("data"):
            files.append(base64.b64decode(item["data"]))
        elif kind == "resource_link" and item.get("uri", "").startswith("https://"):
            urls.append(item["uri"])
        elif kind == "text":
            urls += _URL.findall(item.get("text", ""))
    if urls and not files:
        with httpx.Client(timeout=60, follow_redirects=True) as http:
            for url in urls[:MAX_FILES]:
                res = http.get(url)
                if res.status_code == 200 and res.content[8:12] == b".FIT":
                    files.append(res.content)
    return [f for f in files if f[8:12] == b".FIT"]


_RECORD = re.compile(r"LabelId:\s*(\d+)\s*\|\s*SportType:\s*(\d+)", re.IGNORECASE)


def records(text: str) -> list[tuple[str, int]]:
    """(labelId, sportType) de cada actividad en el texto de `querySportRecords`."""
    return [(m.group(1), int(m.group(2))) for m in _RECORD.finditer(text)]


def _texts(result: dict) -> str:
    return " ".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")


def _blocked(session: Session, user_id: int, texts: str) -> int:
    # COROS a veces corta la petición con un aviso genérico («anomalies»): se avisa sin romper nada.
    logger.warning("COROS oficial: petición bloqueada (%s)", texts[:200])
    row = session.get(CorosOAuth, user_id)
    if row is not None:
        row.last_error = BLOCKED
        session.add(row)
        session.commit()
    return 0


def sync(
    session: Session, user_id: int, mcp: CorosMcp | None = None, today: date | None = None, days: int = DAYS_BACK
) -> int:
    """
    Importa las actividades nuevas de los últimos `days` días: se listan (`querySportRecords`) y se
    descarga el .FIT de cada una que no esté ya (`downloadActivityFitFiles` con su LabelId).

    Returns:
        Cuántas actividades nuevas.
    """
    from sqlmodel import col, select

    from app.models import Activity

    today = today or date.today()
    mcp = mcp or CorosMcp(session, user_id)
    start = (today - timedelta(days=days)).strftime("%Y%m%d")
    try:
        listing = mcp.call_raw(
            "querySportRecords", {"startDate": start, "endDate": today.strftime("%Y%m%d"), "limit": 50}
        )
    except CorosOAuthError as exc:
        row = session.get(CorosOAuth, user_id)
        if row is not None and row.status != "expired":
            row.last_error = str(exc)[:255]
            session.add(row)
            session.commit()
        raise
    texts = _texts(listing)
    if "anomal" in texts.lower():
        return _blocked(session, user_id, texts)
    found = records(texts)
    known = set(
        session.exec(
            select(Activity.external_id).where(
                Activity.user_id == user_id,
                Activity.source == "coros",
                col(Activity.external_id).in_([label for label, _ in found] or [""]),
            )
        ).all()
    )
    new, blocked = 0, False
    for label, sport in [r for r in found if r[0] not in known][:MAX_FILES]:
        result = mcp.call_raw("downloadActivityFitFiles", {"labelId": label, "sportType": sport})
        if not (files := fit_blobs(result)) and "anomal" in _texts(result).lower():
            _blocked(session, user_id, _texts(result))
            blocked = True
            break
        for data in files[:1]:
            try:
                act = parse_fit(data)
            except FileImportError:
                continue
            _, created = save_imported(session, user_id, act, "coros", label)
            new += created
    row = session.get(CorosOAuth, user_id)
    if row is not None:
        if not blocked:  # si COROS cortó la descarga, no se da la sincronización por buena
            row.last_error = ""
            row.last_sync_at = datetime.now(UTC)
        session.add(row)
        session.commit()
    if new:
        after_import(session, user_id)
    return new
