"""
Credenciales de la app de Oura (OAuth2): las pone el administrador en Admin → Conexiones.

Se guardan en `AppSetting`: el Client ID en claro y el Client Secret y el token de verificación de los
webhooks cifrados (`core.crypto`). Si el panel no tiene nada, se usan las variables de entorno
(`OURA_CLIENT_ID`, `OURA_CLIENT_SECRET`, `OURA_WEBHOOK_TOKEN`), como antes. Los secretos nunca salen
por la API: solo se dice si están puestos.
"""

import secrets
from dataclasses import dataclass

from sqlmodel import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.db import engine
from app.models import AppSetting, User
from app.services import accounts

KEY_ID = "oura_client_id"
KEY_SECRET = "oura_client_secret_enc"
KEY_WEBHOOK = "oura_webhook_token_enc"


@dataclass(frozen=True)
class OuraCredentials:
    client_id: str
    client_secret: str
    webhook_token: str
    source: str | None  # "panel" | "entorno" | None (sin configurar)

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


def _decrypt(value: str) -> str:
    try:
        return decrypt_secret(value) if value else ""
    except Exception:  # noqa: BLE001 - clave de cifrado cambiada: como si no estuviera puesto
        return ""


def _read(session: Session) -> OuraCredentials:
    client_id = accounts.get_setting(session, KEY_ID, "")
    secret = _decrypt(accounts.get_setting(session, KEY_SECRET, ""))
    webhook = _decrypt(accounts.get_setting(session, KEY_WEBHOOK, ""))
    if client_id and secret:
        return OuraCredentials(client_id, secret, webhook, "panel")
    env = get_settings()
    if env.oura_client_id and env.oura_client_secret:
        return OuraCredentials(env.oura_client_id, env.oura_client_secret, webhook or env.oura_webhook_token,
                               "entorno")  # fmt: skip
    return OuraCredentials("", "", webhook or env.oura_webhook_token, None)


def credentials(session: Session | None = None) -> OuraCredentials:
    """Credenciales vigentes: las del panel y, si no hay, las del entorno."""
    if session is not None:
        return _read(session)
    with Session(engine) as own:
        return _read(own)


def save(session: Session, admin: User | None, *, client_id: str, client_secret: str | None,
         new_webhook_token: bool = False) -> OuraCredentials:  # fmt: skip
    """
    Guarda las credenciales del panel. `client_secret` vacío o None conserva el que había.
    Sin token de webhooks todavía (o con `new_webhook_token`), se genera uno aleatorio.

    Raises:
        ValueError: Si falta el Client ID, o el Client Secret y no había uno guardado.
    """
    client_id = client_id.strip()
    if not client_id:
        raise ValueError("Falta el Client ID.")
    had_secret = bool(_decrypt(accounts.get_setting(session, KEY_SECRET, "")))
    if not (client_secret and client_secret.strip()) and not had_secret:
        raise ValueError("Falta el Client Secret.")
    accounts.set_setting(session, KEY_ID, client_id)
    if client_secret and client_secret.strip():
        accounts.set_setting(session, KEY_SECRET, encrypt_secret(client_secret.strip()))
    if new_webhook_token or not _decrypt(accounts.get_setting(session, KEY_WEBHOOK, "")):
        accounts.set_setting(session, KEY_WEBHOOK, encrypt_secret(secrets.token_hex(24)))
    accounts.audit(session, admin, "settings.oura", None, client_id=client_id,
                   secreto="cambiado" if client_secret else "sin cambios",
                   token_webhooks="nuevo" if new_webhook_token else "sin cambios")  # fmt: skip
    session.commit()
    return _read(session)


def clear(session: Session, admin: User | None) -> None:
    """Quita las credenciales del panel (si hay variables de entorno, se vuelven a usar esas)."""
    for key in (KEY_ID, KEY_SECRET, KEY_WEBHOOK):
        row = session.get(AppSetting, key)
        if row is not None:
            session.delete(row)
    accounts.audit(session, admin, "settings.oura_cleared", None)
    session.commit()
