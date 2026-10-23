"""
Notificaciones en el móvil (Web Push con VAPID): claves del servidor, suscripciones por dispositivo,
preferencias por tipo de aviso y envío sin repetir el mismo aviso (registro por clave).

Las claves VAPID se generan solas la primera vez y se guardan cifradas en la BD: no hay nada que
configurar en el `.env`. El envío solo se permite a los servicios push de los navegadores (evita que
una suscripción falsa haga que el servidor llame a direcciones internas).
"""

import base64
import json
import logging
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.core.crypto import decrypt_secret, encrypt_secret
from app.models import (
    NotificationLog,
    NotificationPrefs,
    PlannedSession,
    PushSubscription,
    User,
    UserStatus,
)
from app.services import accounts

logger = logging.getLogger(__name__)

VAPID_SETTING = "push.vapid"
TTL_S = 12 * 3600

# Servicios push de los navegadores: Chrome/Android (FCM), Firefox, Safari/iOS y Edge (WNS).
PUSH_HOSTS = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)

# Tipo de aviso → preferencia que lo activa.
KINDS = {
    "daily_session": "daily_session",
    "overload": "overload",
    "sync_error": "sync_error",
    "achievement": "achievements",
    "plan_change": "plan_changes",
    "activity_review": "activity_reviews",
    "test": "tests",
    "weekly_review": "weekly_review",
}


def allowed_endpoint(endpoint: str) -> bool:
    """Solo HTTPS y hacia un servicio push conocido."""
    url = urlparse(endpoint)
    host = (url.hostname or "").lower()
    return url.scheme == "https" and any(host == h or host.endswith(f".{h}") for h in PUSH_HOSTS)


# ─── Claves VAPID ────────────────────────────────────────────────────────────


def _public_b64(vapid: Vapid02) -> str:
    raw = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def vapid_keys(session: Session) -> tuple[Vapid02, str]:
    """Clave privada del servidor y la pública (base64url) que necesita el navegador para suscribirse."""
    stored = accounts.get_setting(session, VAPID_SETTING, "")
    if stored:
        data = json.loads(stored)
        return Vapid02.from_pem(decrypt_secret(data["private_enc"]).encode()), data["public"]
    vapid = Vapid02()
    vapid.generate_keys()
    public = _public_b64(vapid)
    pem = vapid.private_pem().decode()
    accounts.set_setting(session, VAPID_SETTING, json.dumps({"public": public, "private_enc": encrypt_secret(pem)}))
    try:
        session.commit()
    except IntegrityError:  # otro proceso las creó a la vez: se usan las suyas
        session.rollback()
        return vapid_keys(session)
    return vapid, public


def _subject(session: Session) -> str:
    """Contacto del remitente que piden los servicios push (Apple exige mailto: o https:)."""
    admin = next(iter(accounts.admins(session)), None)
    return f"mailto:{admin.email}" if admin else "mailto:admin@example.com"


# ─── Preferencias y suscripciones ────────────────────────────────────────────


def get_prefs(session: Session, user_id: int) -> NotificationPrefs:
    return session.get(NotificationPrefs, user_id) or NotificationPrefs(user_id=user_id)


def subscriptions(session: Session, user_id: int) -> list[PushSubscription]:
    return list(session.exec(select(PushSubscription).where(PushSubscription.user_id == user_id)).all())


def subscribe(session: Session, user_id: int, endpoint: str, p256dh: str, auth: str, user_agent: str) -> None:
    """Alta o actualización por endpoint (si el dispositivo cambia de cuenta, pasa a la nueva)."""
    sub = session.exec(select(PushSubscription).where(PushSubscription.endpoint == endpoint)).first()
    sub = sub or PushSubscription(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth)
    sub.user_id, sub.p256dh, sub.auth, sub.user_agent = user_id, p256dh, auth, user_agent[:255]
    session.add(sub)
    session.commit()


def unsubscribe(session: Session, user_id: int, endpoint: str) -> None:
    sub = session.exec(select(PushSubscription).where(
        PushSubscription.endpoint == endpoint, PushSubscription.user_id == user_id
    )).first()  # fmt: skip
    if sub is not None:
        session.delete(sub)
        session.commit()


# ─── Envío ───────────────────────────────────────────────────────────────────


def deliver(sub: PushSubscription, payload: str, vapid: Vapid02, subject: str) -> None:
    """Envía un mensaje cifrado a un dispositivo (aislado para poder simularlo en los tests)."""
    webpush(
        subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
        data=payload,
        vapid_private_key=vapid,
        vapid_claims={"sub": subject},
        ttl=TTL_S,
        timeout=10,
    )


def push(session: Session, user_id: int, title: str, body: str, url: str = "/", tag: str = "") -> dict:
    """
    Envía a todos los dispositivos del usuario. Las suscripciones caducadas (404/410) se borran.

    Returns:
        {"sent": n, "failed": n}
    """
    subs = [s for s in subscriptions(session, user_id) if allowed_endpoint(s.endpoint)]
    if not subs:
        return {"sent": 0, "failed": 0}
    vapid, _ = vapid_keys(session)
    subject = _subject(session)
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag or title})
    sent = failed = 0
    for sub in subs:
        try:
            deliver(sub, payload, vapid, subject)
            sub.last_ok_at = datetime.now(UTC)
            session.add(sub)
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):  # el navegador anuló la suscripción
                session.delete(sub)
            else:
                logger.warning("Fallo al enviar una notificación push (HTTP %s)", status)
            failed += 1
        except Exception:  # noqa: BLE001 - un dispositivo no debe impedir avisar a los demás
            logger.warning("Fallo de red al enviar una notificación push")
            failed += 1
    session.commit()
    return {"sent": sent, "failed": failed}


def notify(session: Session, user_id: int, kind: str, key: str, title: str, body: str, url: str = "/") -> bool:
    """
    Aviso de un tipo concreto: respeta las preferencias y no repite la misma `key`.

    Returns:
        True si llegó al menos a un dispositivo.
    """
    prefs = get_prefs(session, user_id)
    if not getattr(prefs, KINDS[kind]):
        return False
    exists = session.exec(select(NotificationLog).where(
        NotificationLog.user_id == user_id, NotificationLog.key == key
    )).first()  # fmt: skip
    if exists is not None:
        return False
    if push(session, user_id, title, body, url, tag=kind)["sent"] == 0:
        return False
    session.add(NotificationLog(user_id=user_id, kind=kind, key=key, title=title[:120]))
    session.commit()
    return True


# ─── Avisos concretos ────────────────────────────────────────────────────────


def _local_now(prefs: NotificationPrefs, now: datetime) -> datetime:
    try:
        return now.astimezone(ZoneInfo(prefs.timezone))
    except (ZoneInfoNotFoundError, ValueError):
        return now.astimezone(ZoneInfo("Europe/Madrid"))


def daily_session(session: Session, user_id: int, now: datetime | None = None) -> bool:
    """«Hoy toca…» a la hora elegida si hay sesiones planificadas para hoy (una vez al día)."""
    prefs = get_prefs(session, user_id)
    local = _local_now(prefs, now or datetime.now(UTC))
    if not prefs.daily_session or local.hour != prefs.daily_hour:
        return False
    today: date = local.date()
    planned = session.exec(select(PlannedSession).where(
        PlannedSession.user_id == user_id, PlannedSession.day == today, col(PlannedSession.activity_id).is_(None)
    )).all()  # fmt: skip
    if not planned:
        return False
    title = "Hoy toca: " + planned[0].title if len(planned) == 1 else f"Hoy tienes {len(planned)} sesiones"
    body = " · ".join(p.title for p in planned) if len(planned) > 1 else "Ábrela para ver los ritmos y bloques."
    url = f"/plan/{planned[0].id}" if len(planned) == 1 else "/plan"
    return notify(session, user_id, "daily_session", f"daily:{today.isoformat()}", title, body, url)


def daily_all(session: Session, now: datetime | None = None) -> int:
    """Recorre a quien tiene algún dispositivo suscrito (lo llama Celery cada 15 minutos)."""
    users = session.exec(select(PushSubscription.user_id).distinct()).all()
    count = 0
    for uid in users:
        user = session.get(User, uid)
        if user is not None and user.status == UserStatus.ACTIVE and daily_session(session, uid, now):
            count += 1
    return count


def overload(session: Session, user_id: int, report: dict, today: date | None = None) -> bool:
    """Riesgo de lesión en «Atención»: como mucho un aviso por semana."""
    if report.get("status") != "alert":
        return False
    year, week, _ = (today or date.today()).isocalendar()
    worst = next(c for c in report["checks"] if c["status"] == "alert")
    return notify(session, user_id, "overload", f"overload:{year}-{week}", worst["title"], worst["message"],
                  "/progresion#lesiones")  # fmt: skip


def sync_failed(session: Session, user_id: int, not_connected: bool, today: date | None = None) -> bool:
    """Sincronización fallida: como mucho un aviso al día."""
    day = (today or date.today()).isoformat()
    body = (
        "Tu conexión con Garmin ha caducado. Vuelve a conectarla en Ajustes."
        if not_connected
        else "No se pudieron descargar tus actividades. Lo reintentaremos solos."
    )
    return notify(session, user_id, "sync_error", f"sync:{day}", "Problema con Garmin", body, "/ajustes")


def plan_changed(session: Session, user_id: int, plan_id: int, week: int, reason: str) -> bool:
    return notify(session, user_id, "plan_change", f"plan:{plan_id}:{week}", "Tu plan se ha ajustado", reason,
                  "/plan/entrenamiento")  # fmt: skip


def recent_log(session: Session, user_id: int, days: int = 30) -> list[NotificationLog]:
    since = datetime.now(UTC) - timedelta(days=days)
    return list(session.exec(select(NotificationLog).where(
        NotificationLog.user_id == user_id, NotificationLog.sent_at >= since
    ).order_by(col(NotificationLog.sent_at).desc()).limit(20)).all())  # fmt: skip
