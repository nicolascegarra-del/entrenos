"""
Envoltorio aislado de la librería no oficial `garminconnect`.

Todo acceso a Garmin pasa por aquí: si la librería cambia o se sustituye por la
API oficial o por importación de .FIT, solo hay que tocar este módulo.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from garminconnect import Garmin, GarminConnectAuthenticationError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class GarminNotConnectedError(Exception):
    """No hay tokens válidos: hay que iniciar sesión con `python -m app.cli garmin-login`."""


class GarminSource(Protocol):
    """Lo que necesita el servicio de sincronización (permite usar un falso en tests)."""

    def get_activities(self, start: int, limit: int) -> list[dict]: ...
    def get_activity_details(self, activity_id: int) -> dict | None: ...
    def get_activity_splits(self, activity_id: int) -> dict | None: ...
    def download_fit(self, activity_id: int) -> bytes | None: ...
    def get_devices(self) -> list[dict]: ...
    def get_daily(self, day: str) -> dict[str, Any]: ...


def _token_dir(user_id: int) -> Path:
    # Un directorio de tokens por usuario de la app (cada uno con su cuenta de Garmin).
    return Path(get_settings().garmin_token_dir) / str(user_id)


def has_tokens(user_id: int) -> bool:
    directory = _token_dir(user_id)
    return directory.exists() and any(directory.iterdir())


def login_with_credentials(user_id: int, email: str, password: str, prompt_mfa: Callable[[], str]) -> None:
    """Login interactivo; solo se persisten los tokens, nunca la contraseña."""
    directory = _token_dir(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    Garmin(email=email, password=password, prompt_mfa=prompt_mfa).login(str(directory))


class GarminConnectClient:
    def __init__(self, user_id: int) -> None:
        if not has_tokens(user_id):
            raise GarminNotConnectedError("Garmin no conectado.")
        try:
            self._api = Garmin()
            self._api.login(str(_token_dir(user_id)))
        except (FileNotFoundError, GarminConnectAuthenticationError) as exc:
            raise GarminNotConnectedError(str(exc)) from exc

    def _safe(self, label: str, fn: Callable[[], Any]) -> Any:
        # Un endpoint que falle o no aplique al reloj no debe abortar la sincronización.
        try:
            return fn()
        except GarminConnectAuthenticationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Garmin %s falló: %s", label, type(exc).__name__)
            return None

    def get_activities(self, start: int, limit: int) -> list[dict]:
        return self._api.get_activities(start, limit) or []

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
