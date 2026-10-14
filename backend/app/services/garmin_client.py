"""
Envoltorio aislado de la librería no oficial `garminconnect`.

Todo acceso a Garmin pasa por aquí: si la librería cambia o se sustituye por la
API oficial o por importación de .FIT, solo hay que tocar este módulo.

Los tokens de sesión se guardan cifrados en la BD (`GarminCredential`); la
contraseña de Garmin solo se usa durante el login y nunca se guarda.
"""

import logging
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from cryptography.fernet import Fernet, InvalidToken
from garminconnect import Garmin, GarminConnectAuthenticationError
from sqlmodel import Session

from app.core.config import get_settings
from app.core.db import engine
from app.models import GarminCredential, GarminStatus

logger = logging.getLogger(__name__)


class GarminNotConnectedError(Exception):
    """No hay tokens válidos: hay que conectar Garmin (o reconectar si caducaron)."""


class GarminSource(Protocol):
    """Lo que necesita el servicio de sincronización (permite usar un falso en tests)."""

    def get_activities(self, start: int, limit: int) -> list[dict]: ...
    def get_activity_details(self, activity_id: int) -> dict | None: ...
    def get_activity_splits(self, activity_id: int) -> dict | None: ...
    def download_fit(self, activity_id: int) -> bytes | None: ...
    def get_devices(self) -> list[dict]: ...
    def get_daily(self, day: str) -> dict[str, Any]: ...


# ─── Cifrado de tokens ───────────────────────────────────────────────────────


def _fernet() -> Fernet:
    key = get_settings().garmin_token_key
    if not key:
        raise RuntimeError("Falta GARMIN_TOKEN_KEY para cifrar los tokens de Garmin.")
    return Fernet(key.encode())


def encrypt_tokens(tokens_json: str) -> str:
    return _fernet().encrypt(tokens_json.encode()).decode()


def decrypt_tokens(tokens_enc: str) -> str:
    return _fernet().decrypt(tokens_enc.encode()).decode()


def save_tokens(session: Session, user_id: int, tokens_json: str, display_name: str | None = None) -> None:
    credential = session.get(GarminCredential, user_id) or GarminCredential(user_id=user_id, tokens_enc="")
    credential.tokens_enc = encrypt_tokens(tokens_json)
    credential.status = GarminStatus.OK
    credential.last_ok_at = datetime.now(UTC)
    if display_name:
        credential.display_name = display_name
    session.add(credential)
    session.commit()


def disconnect(session: Session, user_id: int) -> None:
    credential = session.get(GarminCredential, user_id)
    if credential:
        session.delete(credential)
        session.commit()


# ─── Migración de tokens antiguos en fichero ─────────────────────────────────


def _legacy_dir(user_id: int) -> Path:
    return Path(get_settings().garmin_token_dir) / str(user_id)


def migrate_legacy_tokens(session: Session, user_id: int) -> bool:
    """Si quedan tokens en fichero (versión anterior), los cifra en la BD y borra el fichero."""
    token_file = _legacy_dir(user_id) / "garmin_tokens.json"
    if session.get(GarminCredential, user_id) or not token_file.exists():
        return False
    save_tokens(session, user_id, token_file.read_text(encoding="utf-8"))
    shutil.rmtree(_legacy_dir(user_id), ignore_errors=True)
    logger.info("Tokens de Garmin migrados a la BD (usuario %s)", user_id)
    return True


def has_tokens(user_id: int) -> bool:
    """¿Hay una conexión de Garmin utilizable (no caducada)?"""
    with Session(engine) as session:
        migrate_legacy_tokens(session, user_id)
        credential = session.get(GarminCredential, user_id)
        return credential is not None and credential.status == GarminStatus.OK


# ─── Login con credenciales (conectar desde la web o la CLI) ─────────────────


def connect_with_credentials(
    user_id: int, email: str, password: str, prompt_mfa: Callable[[], str], api_factory: Callable[..., Any] = Garmin
) -> dict:
    """
    Inicia sesión en Garmin y guarda solo los tokens cifrados.

    Args:
        prompt_mfa: Se llama si Garmin pide código de verificación; debe devolver el código.
        api_factory: Constructor del cliente (inyectable en tests).

    Returns:
        Perfil de Garmin (`get_user_profile`) para rellenar el perfil de la app.
    """
    api = api_factory(email=email, password=password, prompt_mfa=prompt_mfa)
    api.login()
    tokens = api.client.dumps()
    display_name = getattr(api, "full_name", None) or getattr(api, "display_name", None)
    with Session(engine) as session:
        save_tokens(session, user_id, tokens, display_name)
    try:
        return api.get_user_profile() or {}
    except Exception:  # noqa: BLE001 - el perfil es opcional
        return {}


# ─── Cliente para sincronizar ────────────────────────────────────────────────


class GarminConnectClient:
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        with Session(engine) as session:
            migrate_legacy_tokens(session, user_id)
            credential = session.get(GarminCredential, user_id)
            if credential is None or credential.status != GarminStatus.OK:
                raise GarminNotConnectedError("Garmin no conectado.")
            try:
                tokens = decrypt_tokens(credential.tokens_enc)
            except InvalidToken as exc:
                raise GarminNotConnectedError("No se pudieron descifrar los tokens de Garmin.") from exc
        try:
            self._api = Garmin()
            self._api.login(tokens)  # la librería acepta el JSON de tokens en línea
        except GarminConnectAuthenticationError as exc:
            self._mark_expired()
            raise GarminNotConnectedError("La sesión de Garmin ha caducado: vuelve a conectar.") from exc

    def _mark_expired(self) -> None:
        with Session(engine) as session:
            credential = session.get(GarminCredential, self.user_id)
            if credential:
                credential.status = GarminStatus.EXPIRED
                session.add(credential)
                session.commit()

    def persist(self) -> None:
        """Guarda los tokens (Garmin los renueva durante el uso) tras una sincronización correcta."""
        name = getattr(self._api, "full_name", None) or getattr(self._api, "display_name", None)
        with Session(engine) as session:
            save_tokens(session, self.user_id, self._api.client.dumps(), name)

    def get_user_profile(self) -> dict:
        return self._safe("profile", self._api.get_user_profile) or {}

    def _safe(self, label: str, fn: Callable[[], Any]) -> Any:
        # Un endpoint que falle o no aplique al reloj no debe abortar la sincronización.
        try:
            return fn()
        except GarminConnectAuthenticationError:
            self._mark_expired()
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Garmin %s falló: %s", label, type(exc).__name__)
            return None

    def get_activities(self, start: int, limit: int) -> list[dict]:
        try:
            return self._api.get_activities(start, limit) or []
        except GarminConnectAuthenticationError:
            self._mark_expired()
            raise

    def get_activity_details(self, activity_id: int) -> dict | None:
        return self._safe("details", lambda: self._api.get_activity_details(activity_id, maxchart=10000))

    def get_activity_splits(self, activity_id: int) -> dict | None:
        return self._safe("splits", lambda: self._api.get_activity_splits(activity_id))

    def download_fit(self, activity_id: int) -> bytes | None:
        return self._safe(
            "fit",
            lambda: self._api.download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL),
        )

    def get_devices(self) -> list[dict]:
        return self._safe("devices", self._api.get_devices) or []

    def get_daily(self, day: str) -> dict[str, Any]:
        return {
            "stats": self._safe("stats", lambda: self._api.get_stats(day)),
            "hrv": self._safe("hrv", lambda: self._api.get_hrv_data(day)),
            "sleep": self._safe("sleep", lambda: self._api.get_sleep_data(day)),
            "max_metrics": self._safe("max_metrics", lambda: self._api.get_max_metrics(day)),
        }
