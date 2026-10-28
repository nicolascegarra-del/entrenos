"""
Cliente HTTP de la API v2 de Oura (https://cloud.ouraring.com/v2/docs).

- Bearer con el access token de la persona; se renueva solo antes de caducar o si Oura responde 401.
- Paginación con `next_token` (listas `{data, next_token}`).
- Reintentos con espera creciente en 429 y 5xx, respetando `Retry-After` (límite por token y por app).
- Nunca se registran tokens en los logs.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlmodel import Session

from app.core.crypto import decrypt_secret
from app.models import OuraConnection

logger = logging.getLogger(__name__)

API_URL = "https://api.ouraring.com"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MAX_RETRIES = 4
MAX_WAIT_S = 60.0
MAX_PAGES = 200
# Los tests sustituyen el transporte por un `httpx.MockTransport` (nunca se llama a la API real).
TRANSPORT: httpx.BaseTransport | None = None
sleep: Callable[[float], None] = time.sleep


class OuraError(Exception):
    """Fallo al hablar con Oura (mensaje apto para enseñar)."""


class OuraAuthError(OuraError):
    """La conexión ha caducado o se ha revocado: hay que volver a conectar."""


class OuraScopeError(OuraError):
    """La persona no dio permiso para ese tipo de dato (o su anillo/suscripción no lo tiene)."""


def http() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, transport=TRANSPORT, headers={"User-Agent": "KTrain"})


def _wait(res: httpx.Response, attempt: int) -> float:
    try:
        return min(float(res.headers.get("retry-after", "")), MAX_WAIT_S)
    except ValueError:
        return min(2.0**attempt, MAX_WAIT_S)


def send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Petición con reintentos en 429/5xx y errores de red (devuelve la última respuesta)."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with http() as client:
                res = client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt == MAX_RETRIES:
                break
            sleep(min(2.0**attempt, MAX_WAIT_S))
            continue
        if res.status_code == 429 or res.status_code >= 500:
            if attempt == MAX_RETRIES:
                return res
            logger.info("Oura respondió %s; reintento %s", res.status_code, attempt + 1)
            sleep(_wait(res, attempt))
            continue
        return res
    raise OuraError("Oura no responde ahora mismo. Lo reintentaremos solos.") from last_exc


class OuraClient:
    """API de Oura para una persona (renueva el token cuando hace falta)."""

    def __init__(self, session: Session, conn: OuraConnection) -> None:
        if conn.status == "expired":
            raise OuraAuthError("La conexión con Oura ha caducado: vuelve a conectarla.")
        self.session, self.conn = session, conn

    def _token(self) -> str:
        from app.services.oura_oauth import refresh

        if self.conn.expires_at and self.conn.expires_at - timedelta(minutes=2) <= datetime.now(UTC):
            refresh(self.session, self.conn)
        return decrypt_secret(self.conn.access_token_enc)

    def get(self, path: str, params: dict | None = None, retry_auth: bool = True) -> dict | None:
        """GET a `/v2/usercollection/...`. None si el documento no existe (404)."""
        from app.services.oura_oauth import refresh

        headers = {"Authorization": f"Bearer {self._token()}"}
        res = send("GET", f"{API_URL}{path}", params=params or {}, headers=headers)
        if res.status_code == 401 and retry_auth:
            refresh(self.session, self.conn)  # si el token ya no vale, esto lanza OuraAuthError
            return self.get(path, params, retry_auth=False)
        if res.status_code == 401:
            # Con un token recién renovado, un 401 no es caducidad: Oura lo devuelve para los tipos de dato
            # cuyo permiso no se concedió (p. ej. la configuración del anillo). Se salta solo ese tipo.
            raise OuraScopeError(f"Sin permiso para {path.rsplit('/', 1)[-1]}.")
        if res.status_code == 403:
            raise OuraScopeError(f"Sin permiso para {path.rsplit('/', 1)[-1]}.")
        if res.status_code == 404:
            return None
        if res.status_code >= 400:
            logger.warning("Oura: %s respondió %s", path, res.status_code)
            raise OuraError("Oura no está disponible ahora mismo. Lo reintentaremos solos.")
        try:
            return res.json()
        except ValueError as exc:
            raise OuraError("Oura devolvió una respuesta que no se entiende.") from exc

    def collection(self, name: str, **params: Any) -> list[dict]:
        """Todos los documentos de una colección (`daily_sleep`, `heartrate`…) siguiendo `next_token`."""
        out: list[dict] = []
        query = {k: v for k, v in params.items() if v is not None}
        for _ in range(MAX_PAGES):
            page = self.get(f"/v2/usercollection/{name}", query) or {}
            out.extend(d for d in page.get("data") or [] if isinstance(d, dict))
            token = page.get("next_token")
            if not token:
                break
            query = {**query, "next_token": token}
        return out

    def document(self, name: str, document_id: str) -> dict | None:
        return self.get(f"/v2/usercollection/{name}/{document_id}")

    def personal_info(self) -> dict:
        return self.get("/v2/usercollection/personal_info") or {}
