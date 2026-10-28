"""
Webhooks de Oura: suscripciones de la app y comprobación de los avisos que llegan.

- Suscripciones (`/v2/webhook/subscription`, cabeceras `x-client-id` / `x-client-secret`): una por tipo de
  dato × evento (create, update, delete). Caducan: se renuevan las que caducan en menos de 7 días.
  Solo con id/secreto de la app, token de verificación y una URL pública https.
- Verificación: Oura hace GET a la URL con `verification_token` y `challenge`; se devuelve el `challenge`.
- Avisos: POST con `x-oura-signature` = HMAC-SHA256 (hex en mayúsculas) con el secreto de la app sobre
  `timestamp + cuerpo`, y `x-oura-timestamp`. Se rechazan firmas malas y avisos de hace más de 5 minutos.
"""

import hashlib
import hmac
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.core.config import get_settings
from app.models import OuraWebhookSubscription
from app.services import oura_client
from app.services.oura_sync import WEBHOOK_TYPES

logger = logging.getLogger(__name__)

SUBSCRIPTION_URL = f"{oura_client.API_URL}/v2/webhook/subscription"
WEBHOOK_PATH = "/api/v1/sources/oura/webhook"
EVENT_TYPES = ("create", "update", "delete")
RENEW_BEFORE = timedelta(days=7)
MAX_AGE = timedelta(minutes=5)


def callback_url() -> str:
    from app.services.mailer import link

    return link(WEBHOOK_PATH)


def enabled() -> str | None:
    """None si se pueden usar los webhooks; si no, el motivo."""
    settings = get_settings()
    if not settings.oura_configured:
        return "Falta OURA_CLIENT_ID / OURA_CLIENT_SECRET."
    if not settings.oura_webhook_token:
        return "Falta OURA_WEBHOOK_TOKEN."
    if urlparse(callback_url()).scheme != "https":
        return "La URL pública (APP_PUBLIC_URL) no es https."
    return None


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {"x-client-id": settings.oura_client_id, "x-client-secret": settings.oura_client_secret}


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).hexdigest().upper()


def _timestamp(value: str) -> datetime | None:
    try:
        number = float(value)
    except ValueError:
        try:
            t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    if number > 1e12:  # milisegundos
        number /= 1000
    return datetime.fromtimestamp(number, UTC)


def valid_signature(body: bytes, signature: str | None, timestamp: str | None, now: datetime | None = None) -> bool:
    """Firma correcta y aviso reciente (≤ 5 min)."""
    secret = get_settings().oura_client_secret
    if not secret or not signature or not timestamp:
        return False
    when = _timestamp(timestamp)
    if when is None or abs((now or datetime.now(UTC)) - when) > MAX_AGE:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature.strip().upper())


def valid_verification(token: str | None) -> bool:
    expected = get_settings().oura_webhook_token
    return bool(expected and token) and hmac.compare_digest(str(token), expected)


def _parse_expiration(value: object) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _upsert(session: Session, remote: dict) -> OuraWebhookSubscription:
    row = session.exec(
        select(OuraWebhookSubscription).where(OuraWebhookSubscription.remote_id == str(remote["id"]))
    ).first() or OuraWebhookSubscription(remote_id=str(remote["id"]), data_type="", event_type="", callback_url="")
    row.data_type = str(remote.get("data_type") or row.data_type)[:40]
    row.event_type = str(remote.get("event_type") or row.event_type)[:16]
    row.callback_url = str(remote.get("callback_url") or row.callback_url)[:500]
    row.expiration_time = _parse_expiration(remote.get("expiration_time")) or row.expiration_time
    session.add(row)
    return row


def ensure_subscriptions(session: Session, now: datetime | None = None) -> dict:
    """
    Crea las suscripciones que falten (todos los tipos × create/update/delete) y renueva las que caducan
    en menos de 7 días. Devuelve un resumen (o el motivo por el que no se hace nada).
    """
    reason = enabled()
    if reason:
        return {"skipped": reason}
    now = now or datetime.now(UTC)
    url = callback_url()
    res = oura_client.send("GET", SUBSCRIPTION_URL, headers=_headers())
    if res.status_code >= 400:
        logger.warning("Oura: no se pudieron leer las suscripciones (%s)", res.status_code)
        return {"error": res.status_code}
    remote = [r for r in (res.json() or []) if isinstance(r, dict) and r.get("id")]
    for r in remote:
        _upsert(session, r)
    # Las locales que ya no existen en Oura se olvidan.
    ids = {str(r["id"]) for r in remote}
    for row in session.exec(select(OuraWebhookSubscription)).all():
        if row.remote_id not in ids:
            session.delete(row)
    session.commit()
    mine = {(r.get("data_type"), r.get("event_type")): r for r in remote if r.get("callback_url") == url}
    created = renewed = failed = 0
    for data_type in WEBHOOK_TYPES:
        for event_type in EVENT_TYPES:
            current = mine.get((data_type, event_type))
            if current is None:
                body = {"callback_url": url, "verification_token": get_settings().oura_webhook_token,
                        "event_type": event_type, "data_type": data_type}  # fmt: skip
                r = oura_client.send("POST", SUBSCRIPTION_URL, json=body, headers=_headers())
                if r.status_code < 400 and isinstance(r.json(), dict) and r.json().get("id"):
                    _upsert(session, r.json())
                    created += 1
                else:
                    logger.warning("Oura: no se pudo suscribir %s/%s (%s)", data_type, event_type, r.status_code)
                    failed += 1
                continue
            expires = _parse_expiration(current.get("expiration_time"))
            if expires is None or expires - now < RENEW_BEFORE:
                r = oura_client.send("PUT", f"{SUBSCRIPTION_URL}/renew/{current['id']}", headers=_headers())
                if r.status_code < 400 and isinstance(r.json(), dict):
                    _upsert(session, {**current, **r.json()})
                    renewed += 1
                else:
                    failed += 1
    session.commit()
    return {"created": created, "renewed": renewed, "failed": failed}
