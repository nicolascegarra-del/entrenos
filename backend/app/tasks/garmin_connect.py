"""
Conexión con Garmin desde la web.

El estado del login con código de verificación (MFA) vive dentro del cliente de
`garminconnect` y no se puede guardar entre peticiones HTTP (la API tiene varios
procesos). Por eso el login completo se hace en una tarea del worker, que espera el
código en Redis. La contraseña viaja cifrada en el mensaje de la tarea y nunca se
guarda ni se registra en logs.
"""

import logging
import secrets
import time
from collections.abc import Callable
from typing import Any

import redis
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from sqlmodel import Session

from app.core.config import get_settings
from app.core.db import engine
from app.services.garmin_client import connect_with_credentials, decrypt_tokens, encrypt_tokens
from app.services.profile import apply_garmin_profile
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

STATE_TTL_S = 15 * 60
MFA_WAIT_S = 5 * 60
PENDING, NEEDS_MFA, VERIFYING, CONNECTED, ERROR = "pending", "needs_mfa", "verifying", "connected", "error"


def _redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def _key(connect_id: str) -> str:
    return f"garmin-connect:{connect_id}"


def set_state(connect_id: str, **fields: Any) -> None:
    r = _redis()
    r.hset(_key(connect_id), mapping={k: "" if v is None else str(v) for k, v in fields.items()})
    r.expire(_key(connect_id), STATE_TTL_S)


def get_state(connect_id: str) -> dict[str, str]:
    return _redis().hgetall(_key(connect_id))


def submit_mfa_code(connect_id: str, code: str) -> None:
    r = _redis()
    r.set(f"{_key(connect_id)}:code", encrypt_tokens(code), ex=MFA_WAIT_S)


def start_connect(user_id: int, email: str, password: str) -> str:
    """Encola el login; devuelve el id con el que la web consulta el estado."""
    connect_id = secrets.token_urlsafe(16)
    set_state(connect_id, user_id=user_id, status=PENDING, error=None)
    connect_task.delay(connect_id, user_id, email, encrypt_tokens(password))
    return connect_id


def _wait_for_code(connect_id: str, sleep: Callable[[float], None] = time.sleep) -> str:
    set_state(connect_id, status=NEEDS_MFA)
    r = _redis()
    deadline = time.monotonic() + MFA_WAIT_S
    while time.monotonic() < deadline:
        encrypted = r.getdel(f"{_key(connect_id)}:code")
        if encrypted:
            set_state(connect_id, status=VERIFYING)
            return decrypt_tokens(encrypted)
        sleep(1)
    raise TimeoutError("No llegó el código de verificación a tiempo.")


def run_connect(
    connect_id: str, user_id: int, email: str, password_enc: str, api_factory: Callable[..., Any] = Garmin
) -> str:
    """Hace el login (con MFA si Garmin lo pide), guarda los tokens y rellena el perfil."""
    try:
        password = decrypt_tokens(password_enc)
        garmin_profile = connect_with_credentials(
            user_id, email, password, prompt_mfa=lambda: _wait_for_code(connect_id), api_factory=api_factory
        )
        del password
        with Session(engine) as session:
            apply_garmin_profile(session, user_id, garmin_profile)
        set_state(connect_id, status=CONNECTED)
        return CONNECTED
    except GarminConnectAuthenticationError:
        message = "Email, contraseña o código de Garmin incorrectos."
    except GarminConnectTooManyRequestsError:
        message = "Garmin ha bloqueado temporalmente los intentos. Espera unos minutos."
    except TimeoutError as exc:
        message = str(exc)
    except GarminConnectConnectionError:
        message = "No se pudo contactar con Garmin. Inténtalo más tarde."
    except Exception as exc:  # noqa: BLE001 - no exponer detalles internos al usuario
        logger.warning("Error conectando Garmin: %s", type(exc).__name__)
        message = "No se pudo conectar con Garmin."
    set_state(connect_id, status=ERROR, error=message)
    return ERROR


@celery_app.task(name="garmin.connect", ignore_result=True)
def connect_task(connect_id: str, user_id: int, email: str, password_enc: str) -> str:
    return run_connect(connect_id, user_id, email, password_enc)
