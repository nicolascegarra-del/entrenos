"""
Traer las actividades de COROS por la conexión oficial (MCP con OAuth).

Las herramientas de consulta devuelven texto pensado para un asistente, así que no se interpreta la
lista: se descargan directamente los .FIT de los últimos días (`downloadActivityFitFiles`), que traen
todo (deporte, ruta, pulso, potencia, vueltas) y se leen con el mismo lector que cualquier FIT. Si el
servidor manda enlaces en vez del fichero, se descargan de esos enlaces.

COROS limita a 50 ficheros al día: se piden como mucho 10 por pasada y solo de hoy y ayer, cada 6 h.
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

DAYS_BACK = 1  # hoy y ayer
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


def sync(session: Session, user_id: int, mcp: CorosMcp | None = None, today: date | None = None) -> int:
    """
    Importa las actividades de hoy y ayer.

    Returns:
        Cuántas actividades nuevas.
    """
    today = today or date.today()
    mcp = mcp or CorosMcp(session, user_id)
    start = (today - timedelta(days=DAYS_BACK)).strftime("%Y%m%d")
    try:
        result = mcp.call_raw(
            "downloadActivityFitFiles", {"startDate": start, "endDate": today.strftime("%Y%m%d"), "limit": MAX_FILES}
        )
    except CorosOAuthError as exc:
        row = session.get(CorosOAuth, user_id)
        if row is not None and row.status != "expired":
            row.last_error = str(exc)[:255]
            session.add(row)
            session.commit()
        raise
    files = fit_blobs(result)
    texts = " ".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    if not files and "anomal" in texts.lower():
        # COROS a veces no deja descargar las actividades por esta vía (aviso genérico): se avisa sin romper nada.
        logger.warning("COROS oficial: descarga de actividades bloqueada (%s)", texts[:200])
        row = session.get(CorosOAuth, user_id)
        if row is not None:
            row.last_error = BLOCKED
            session.add(row)
            session.commit()
        return 0
    new = 0
    for data in files:
        try:
            act = parse_fit(data)
        except FileImportError:
            continue
        _, created = save_imported(session, user_id, act, "coros", f"fit:{act.start_time.isoformat()}")
        new += created
    row = session.get(CorosOAuth, user_id)
    if row is not None:
        row.last_error = ""
        row.last_sync_at = datetime.now(UTC)
        session.add(row)
        session.commit()
    if new:
        after_import(session, user_id)
    return new
