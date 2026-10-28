"""
Conexión con el anillo Oura por OAuth2 (authorization code).

1. `start`: `state` de un solo uso (15 min) con PKCE S256 y la URL de autorización de Oura.
2. `finish`: la vuelta cambia el código por access + refresh token (cifrados), lee `personal_info`
   (id de Oura para los webhooks y, solo en campos vacíos, peso, altura y sexo del perfil) y encola la
   importación del histórico.
3. `refresh`: Oura da refresh tokens de un solo uso; si lo rechaza, la conexión pasa a `expired` y se avisa.
4. `disconnect`: revoca el token (si se puede), borra la conexión y, con `purge`, todos los datos de Oura.

La edad de `personal_info` NO se convierte en fecha de nacimiento (sería inventarla): no se usa.
"""

import base64
import hashlib
import logging
import secrets
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

from sqlmodel import Session, select

from app.core.crypto import decrypt_secret, encrypt_secret
from app.models import OAuthState, OuraConnection, Sex
from app.services import oura_client, oura_config
from app.services.oura_client import OuraAuthError, OuraError

logger = logging.getLogger(__name__)

PROVIDER = "oura"
AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
TOKEN_URL = "https://api.ouraring.com/oauth/token"
REVOKE_URL = "https://api.ouraring.com/oauth/revoke"
SCOPES = "email personal daily heartrate workout tag session spo2 heart_health"
CALLBACK_PATH = "/api/v1/sources/oura/callback"
STATE_TTL = timedelta(minutes=15)
EXPIRED_MESSAGE = "La conexión con Oura ha caducado: vuelve a conectarla."


class OuraOAuthError(OuraError):
    """Fallo al conectar con Oura (mensaje listo para enseñar)."""


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def start(session: Session, user_id: int, origin: str) -> str:
    """
    Prepara la autorización y devuelve la URL de Oura a la que llevar a la persona.

    Args:
        origin: La web desde la que se conecta: la vuelta llega a `origin + CALLBACK_PATH` (debe estar dada
            de alta como Redirect URI en la app de Oura).

    Raises:
        OuraOAuthError: Si la app de Oura no está configurada.
    """
    creds = oura_config.credentials(session)
    if not creds.configured:
        raise OuraOAuthError("La conexión con Oura no está configurada en este servidor.")
    redirect_uri = origin.rstrip("/") + CALLBACK_PATH
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(32)
    for old in session.exec(
        select(OAuthState).where(OAuthState.user_id == user_id, OAuthState.provider == PROVIDER)
    ).all():
        session.delete(old)
    session.add(OAuthState(state=state, user_id=user_id, provider=PROVIDER, code_verifier=verifier,
                           redirect_uri=redirect_uri))  # fmt: skip
    session.commit()
    params = {
        "response_type": "code",
        "client_id": creds.client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _save_tokens(row: OuraConnection, tokens: dict) -> None:
    row.access_token_enc = encrypt_secret(tokens["access_token"])
    if tokens.get("refresh_token"):
        row.refresh_token_enc = encrypt_secret(tokens["refresh_token"])
    expires = tokens.get("expires_in")
    row.expires_at = datetime.now(UTC) + timedelta(seconds=int(expires)) if expires else None
    if tokens.get("scope"):
        row.scopes = str(tokens["scope"])[:255]
    row.status, row.last_error = "ok", ""


def _token_request(data: dict) -> dict | None:
    creds = oura_config.credentials()
    body = {**data, "client_id": creds.client_id, "client_secret": creds.client_secret}
    res = oura_client.send("POST", TOKEN_URL, data=body)
    try:
        payload = res.json()
    except ValueError:
        payload = {}
    if res.status_code >= 400 or not isinstance(payload, dict) or "access_token" not in payload:
        logger.warning("Oura: petición de token rechazada (%s)", res.status_code)
        return None
    return payload


def pending_state(session: Session, state: str) -> OAuthState | None:
    row = session.get(OAuthState, state) if state else None
    return row if row is not None and row.provider == PROVIDER else None


def finish(session: Session, state: str, code: str) -> int:
    """
    Vuelta de Oura: cambia el código por los tokens, guarda la conexión y encola el histórico.

    Returns:
        El usuario que se ha conectado.

    Raises:
        OuraOAuthError: `state` desconocido o caducado, Oura rechaza el código o el anillo ya está en otra cuenta.
    """
    pending = pending_state(session, state)
    if pending is None or datetime.now(UTC) - pending.created_at > STATE_TTL:
        raise OuraOAuthError("La autorización ha caducado: vuelve a pulsar «Conectar».")
    user_id, redirect_uri, verifier = pending.user_id, pending.redirect_uri, pending.code_verifier
    session.delete(pending)
    session.commit()
    tokens = _token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                             "code_verifier": verifier})  # fmt: skip
    if tokens is None:
        raise OuraOAuthError("Oura no aceptó la autorización. Vuelve a intentarlo.")
    row = session.get(OuraConnection, user_id) or OuraConnection(user_id=user_id, access_token_enc="")
    row.connected_at = datetime.now(UTC)
    _save_tokens(row, tokens)
    session.add(row)
    session.commit()
    try:
        info = oura_client.OuraClient(session, row).personal_info()
    except OuraError:
        info = {}
    oura_id = str(info.get("id") or "")[:64]
    if oura_id:
        other = session.exec(
            select(OuraConnection).where(OuraConnection.oura_user_id == oura_id, OuraConnection.user_id != user_id)
        ).first()
        if other is not None:
            session.delete(row)
            session.commit()
            raise OuraOAuthError("Ese anillo ya está conectado a otra cuenta de KTrain.")
        row.oura_user_id = oura_id
    apply_personal_info(session, user_id, info)
    row.history_status = "running"
    session.add(row)
    session.commit()
    _enqueue_history(user_id)
    from app.services.daily_sources import recompute_user

    recompute_user(session, user_id)  # con «auto», el sueño pasa a salir de Oura
    return user_id


def _enqueue_history(user_id: int) -> None:
    try:
        from app.tasks.oura import oura_import_history_task

        oura_import_history_task.apply_async(args=[user_id], argsrepr="(usuario)")
    except Exception:  # noqa: BLE001 - la sincronización periódica lo traerá igualmente
        logger.warning("No se pudo encolar la importación del histórico de Oura")


def apply_personal_info(session: Session, user_id: int, info: dict) -> None:
    """Rellena SOLO los campos vacíos del perfil (peso, altura en cm, sexo). La edad no se usa."""
    from app.services.profile import get_profile, record_weight

    profile = get_profile(session, user_id)
    changed = False
    weight, height = info.get("weight"), info.get("height")
    if profile.weight_kg is None and isinstance(weight, int | float) and 20 <= weight < 400:
        profile.weight_kg = round(float(weight), 1)
        record_weight(session, user_id, profile.weight_kg, "oura", date.today())
        changed = True
    if profile.height_cm is None and isinstance(height, int | float) and height > 0:
        cm = height * 100 if height < 3 else height  # Oura la da en metros
        if 50 <= cm < 260:
            profile.height_cm, changed = round(float(cm), 1), True
    sex = str(info.get("biological_sex") or "").lower()
    if profile.sex is None and sex in ("male", "female"):
        profile.sex, changed = Sex(sex), True
    if changed:
        session.add(profile)
        session.commit()


def refresh(session: Session, row: OuraConnection) -> None:
    """
    Renueva el access token. Si Oura no lo acepta, la conexión queda `expired` y se avisa a la persona.

    Raises:
        OuraAuthError: Si no se puede renovar.
    """
    tokens = None
    if row.refresh_token_enc:
        tokens = _token_request({"grant_type": "refresh_token", "refresh_token": decrypt_secret(row.refresh_token_enc)})
    if tokens is None:
        mark_expired(session, row)
        raise OuraAuthError(EXPIRED_MESSAGE)
    _save_tokens(row, tokens)
    session.add(row)
    session.commit()


def mark_expired(session: Session, row: OuraConnection) -> None:
    """Conexión caducada: estado `expired` y un aviso (como mucho uno al día)."""
    row.status, row.last_error = "expired", EXPIRED_MESSAGE
    session.add(row)
    session.commit()
    try:
        from app.services.notifications import notify

        notify(session, row.user_id, "sync_error", f"oura-expired:{date.today().isoformat()}",
               "Conexión con Oura caducada", "Vuelve a conectar tu anillo en Ajustes.", "/ajustes")  # fmt: skip
    except Exception:  # noqa: BLE001 - el aviso es secundario
        session.rollback()


def disconnect(session: Session, user_id: int, purge: bool = False) -> None:
    """Revoca el token en Oura (si se puede), borra la conexión y, con `purge`, todos los datos de Oura."""
    row = session.get(OuraConnection, user_id)
    if row is not None:
        try:
            oura_client.send("GET", REVOKE_URL, params={"access_token": decrypt_secret(row.access_token_enc)})
        except Exception:  # noqa: BLE001 - desconectar nunca falla por la revocación
            logger.info("Oura: no se pudo revocar el token")
        session.delete(row)
        session.commit()
    if purge:
        from app.services.oura_sync import purge as purge_data

        purge_data(session, user_id)
    from app.services.daily_sources import recompute_user

    recompute_user(session, user_id)
