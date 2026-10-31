"""
Relojes y pulseras que se conectan con la cuenta de su marca (APIs no oficiales): Suunto, Amazfit (Zepp),
Xiaomi (Mi Fitness) y Samsung Health. Cada marca es un módulo con la misma forma (`Provider`); aquí está lo común:
conectar, guardar la sesión cifrada y sincronizar los entrenos sin duplicarlos.

Ninguna contraseña se guarda: se usa una vez para entrar y solo queda la sesión (cifrada). Todas estas
APIs pueden cambiar sin aviso, así que cualquier fallo se guarda en la conexión y nunca tumba nada más.
"""

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.core.crypto import decrypt_secret, encrypt_secret
from app.models import Activity, DeviceConnection
from app.services.file_import import FileImportError, ImportedActivity, after_import, save_imported

logger = logging.getLogger(__name__)

FIRST_SYNC_DAYS = 90
RECENT_DAYS = 14
MAX_NEW = 40


class DeviceError(RuntimeError):
    """La marca rechazó la petición o no respondió (el mensaje se puede enseñar a la persona)."""


class DeviceExpired(DeviceError):
    """La sesión ya no vale: hay que volver a conectar."""


@dataclass
class RemoteWorkout:
    """Un entreno de la nube de la marca: su id y cómo traerlo entero (solo si aún no lo tenemos)."""

    external_id: str
    start_time: datetime
    fetch: Callable[[], ImportedActivity]


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    # Email + contraseña → (sesión, cuenta a mostrar). None = no se conecta con contraseña (Xiaomi: QR).
    login: Callable[[str, str], tuple[dict, str]] | None
    # Sesión y desde cuándo → entrenos, del más reciente al más antiguo.
    workouts: Callable[[dict, datetime], Iterable[RemoteWorkout]]


def providers() -> dict[str, Provider]:
    from app.services.devices import samsung, suunto, xiaomi, zepp

    return {p.key: p for p in (suunto.PROVIDER, zepp.PROVIDER, xiaomi.PROVIDER, samsung.PROVIDER)}


def get_connection(session: Session, user_id: int, provider: str) -> DeviceConnection | None:
    return session.exec(select(DeviceConnection).where(
        DeviceConnection.user_id == user_id, DeviceConnection.provider == provider
    )).first()  # fmt: skip


def read_session(conn: DeviceConnection) -> dict:
    return json.loads(decrypt_secret(conn.session_enc)) if conn.session_enc else {}


def save_session(
    session: Session, user_id: int, provider: str, data: dict, account: str, status: str = "ok"
) -> DeviceConnection:
    """Guarda (o renueva) la conexión con la sesión cifrada."""
    conn = get_connection(session, user_id, provider) or DeviceConnection(user_id=user_id, provider=provider)
    conn.account, conn.session_enc, conn.status, conn.last_error = (
        account[:255],
        encrypt_secret(json.dumps(data)),
        status,
        "",
    )
    session.add(conn)
    session.commit()
    session.refresh(conn)
    return conn


def connect(session: Session, user_id: int, provider: str, account: str, password: str) -> DeviceConnection:
    """
    Entra en la marca con email y contraseña y guarda solo la sesión.

    Raises:
        DeviceError: credenciales no válidas, marca caída o marca que no admite contraseña.
    """
    p = providers()[provider]
    if p.login is None:
        raise DeviceError(f"{p.label} no se conecta con contraseña.")
    data, shown = p.login(account, password)
    return save_session(session, user_id, provider, data, shown or account)


def disconnect(session: Session, user_id: int, provider: str) -> None:
    conn = get_connection(session, user_id, provider)
    if conn is not None:
        session.delete(conn)
        session.commit()


def _imported(session: Session, user_id: int, provider: str, external_id: str) -> bool:
    return session.exec(select(Activity.id).where(
        Activity.user_id == user_id, Activity.source == provider, Activity.external_id == external_id
    )).first() is not None  # fmt: skip


def sync(session: Session, user_id: int, provider: str, days: int | None = None, max_new: int = MAX_NEW) -> int:
    """
    Trae los entrenos nuevos de la marca (del más reciente hacia atrás; para en el primero ya importado,
    salvo en la primera sincronización). Los que ya estén por otra fuente (p. ej. Garmin) no se duplican.

    Returns:
        Actividades nuevas.
    """
    conn = get_connection(session, user_id, provider)
    if conn is None or conn.status in ("expired", "pending"):
        return 0
    first = conn.last_sync_at is None
    since = datetime.now(UTC) - timedelta(days=days or (FIRST_SYNC_DAYS if first else RECENT_DAYS))
    created = 0
    sess = read_session(conn)
    before = json.dumps(sess, sort_keys=True)
    try:
        # La marca puede apuntar datos en la sesión (p. ej. el registro de Samsung): se guardan al final.
        for remote in providers()[provider].workouts(sess, since):
            if remote.start_time < since:
                break
            if _imported(session, user_id, provider, remote.external_id):
                if first:
                    continue
                break  # ya importada desde esta marca: las anteriores también
            try:
                act = remote.fetch()
            except (FileImportError, ValueError, KeyError, TypeError):
                logger.warning("%s: entreno sin datos importables", provider)
                continue
            _, new = save_imported(session, user_id, act, provider, remote.external_id)
            if new:
                created += 1
                if created >= max_new:
                    break
        conn.status, conn.last_error = "ok", ""
    except DeviceExpired as exc:
        conn.status, conn.last_error = "expired", str(exc)[:255]
    except DeviceError as exc:
        conn.status, conn.last_error = "error", str(exc)[:255]
    conn.last_sync_at = datetime.now(UTC)
    if json.dumps(sess, sort_keys=True) != before:
        conn.session_enc = encrypt_secret(json.dumps(sess))
    session.add(conn)
    session.commit()
    if created:
        after_import(session, user_id)
    return created
