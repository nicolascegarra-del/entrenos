"""
Conexión oficial con COROS: OAuth 2.1 de su servidor MCP (`mcp.coros.com`) y llamadas a sus herramientas.

Flujo (estándar MCP / OAuth 2.1):

1. Descubrimiento: el recurso `https://mcp.coros.com/mcp` publica sus metadatos
   (`/.well-known/oauth-protected-resource/mcp`) con el servidor de autorización de la región
   (p. ej. `mcpeu.coros.com`) y este los suyos (`/.well-known/oauth-authorization-server`).
2. Registro dinámico (RFC 7591) de la app como cliente público (sin secreto), uno por dirección de
   vuelta (`localhost` en desarrollo, la URL pública en producción). Se guarda y se reutiliza.
3. Autorización con PKCE S256 y `state` de un solo uso; la persona entra en COROS y lo autoriza.
4. El código se cambia por un access token y un refresh token (`offline_access`), que se guardan
   cifrados. El access token se renueva solo cuando caduca.

Las herramientas se llaman por JSON-RPC (`tools/call`) en HTTP; la respuesta puede venir como JSON o
como un evento SSE.
"""

import base64
import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from sqlmodel import Session, select

from app.core.crypto import decrypt_secret, encrypt_secret
from app.models import CorosOAuth, OAuthClient, OAuthState

logger = logging.getLogger(__name__)

PROVIDER = "coros"
MCP_URL = "https://mcp.coros.com/mcp"
SCOPE = "openid mcp.tools offline_access"
CALLBACK_PATH = "/api/v1/sources/coros-official/callback"
STATE_TTL = timedelta(minutes=15)
TIMEOUT = 30.0
CLIENT_NAME = "APP ENTRENOS"


class CorosOAuthError(Exception):
    """Fallo de la conexión oficial con COROS (mensaje listo para enseñar)."""


def _http() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": "app-entrenos"})


def discover(mcp_url: str = MCP_URL) -> dict:
    """Metadatos: recurso (región), servidor de autorización y sus endpoints."""
    parsed = urlparse(mcp_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    with _http() as http:
        resource = http.get(f"{base}/.well-known/oauth-protected-resource{parsed.path}").json()
        issuer = resource["authorization_servers"][0]
        server = http.get(f"{issuer.rstrip('/')}/.well-known/oauth-authorization-server").json()
    return {"resource": resource.get("resource") or mcp_url, "issuer": issuer, **server}


def _client_id(session: Session, meta: dict, redirect_uri: str) -> str:
    """Cliente registrado para esa dirección de vuelta (se registra la primera vez)."""
    row = session.exec(
        select(OAuthClient).where(
            OAuthClient.provider == PROVIDER,
            OAuthClient.redirect_uri == redirect_uri,
            OAuthClient.issuer == meta["issuer"],
        )
    ).first()
    if row is not None:
        return row.client_id
    body = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPE,
    }
    with _http() as http:
        res = http.post(meta["registration_endpoint"], json=body)
    if res.status_code >= 400 or "client_id" not in res.json():
        logger.warning("COROS: registro de cliente rechazado (%s)", res.status_code)
        raise CorosOAuthError("COROS no aceptó registrar la app. Inténtalo más tarde.")
    client_id = res.json()["client_id"]
    session.add(OAuthClient(provider=PROVIDER, issuer=meta["issuer"], redirect_uri=redirect_uri, client_id=client_id))
    session.commit()
    return client_id


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def start(session: Session, user_id: int, origin: str) -> str:
    """
    Prepara la autorización y devuelve la URL de COROS a la que llevar a la persona.

    Args:
        origin: la web desde la que se conecta («http://localhost:3000», la URL pública…): la vuelta
            llega ahí para que la sesión siga iniciada.
    """
    meta = discover()
    redirect_uri = origin.rstrip("/") + CALLBACK_PATH
    client_id = _client_id(session, meta, redirect_uri)
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(32)
    # Limpia autorizaciones a medias viejas de esta persona.
    for old in session.exec(select(OAuthState).where(OAuthState.user_id == user_id)).all():
        session.delete(old)
    session.add(OAuthState(state=state, user_id=user_id, provider=PROVIDER, code_verifier=verifier,
                           redirect_uri=redirect_uri))  # fmt: skip
    session.commit()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": meta["resource"],
    }
    return f"{meta['authorization_endpoint']}?{urlencode(params)}"


def _save_tokens(row: CorosOAuth, tokens: dict) -> None:
    row.access_token_enc = encrypt_secret(tokens["access_token"])
    if tokens.get("refresh_token"):
        row.refresh_token_enc = encrypt_secret(tokens["refresh_token"])
    expires = tokens.get("expires_in")
    row.expires_at = datetime.now(UTC) + timedelta(seconds=int(expires)) if expires else None
    row.status, row.last_error = "ok", ""


def finish(session: Session, state: str, code: str) -> int:
    """
    Vuelta de COROS: cambia el código por los tokens y guarda la conexión.

    Returns:
        El usuario que se ha conectado.

    Raises:
        CorosOAuthError: `state` desconocido o caducado, o COROS rechaza el código.
    """
    pending = session.get(OAuthState, state)
    if pending is None or datetime.now(UTC) - pending.created_at > STATE_TTL:
        raise CorosOAuthError("La autorización ha caducado: vuelve a pulsar «Conectar».")
    session.delete(pending)
    session.commit()
    meta = discover()
    client_id = _client_id(session, meta, pending.redirect_uri)
    with _http() as http:
        res = http.post(meta["token_endpoint"], data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": pending.redirect_uri,
            "client_id": client_id, "code_verifier": pending.code_verifier, "resource": meta["resource"],
        })  # fmt: skip
    if res.status_code >= 400 or "access_token" not in res.json():
        logger.warning("COROS: canje de código rechazado (%s)", res.status_code)
        raise CorosOAuthError("COROS no aceptó la autorización. Vuelve a intentarlo.")
    row = session.get(CorosOAuth, pending.user_id) or CorosOAuth(
        user_id=pending.user_id, client_id=client_id, issuer=meta["issuer"], mcp_url=meta["resource"],
        access_token_enc="",
    )  # fmt: skip
    row.client_id, row.issuer, row.mcp_url = client_id, meta["issuer"], meta["resource"]
    row.connected_at = datetime.now(UTC)
    _save_tokens(row, res.json())
    session.add(row)
    session.commit()
    return pending.user_id


def _refresh(session: Session, row: CorosOAuth) -> None:
    if not row.refresh_token_enc:
        raise CorosOAuthError("La conexión con COROS ha caducado: vuelve a conectarla.")
    meta = discover()
    with _http() as http:
        res = http.post(meta["token_endpoint"], data={
            "grant_type": "refresh_token", "refresh_token": decrypt_secret(row.refresh_token_enc),
            "client_id": row.client_id, "resource": row.mcp_url,
        })  # fmt: skip
    if res.status_code >= 400 or "access_token" not in res.json():
        row.status, row.last_error = "expired", "La conexión con COROS ha caducado: vuelve a conectarla."
        session.add(row)
        session.commit()
        raise CorosOAuthError(row.last_error)
    _save_tokens(row, res.json())
    session.add(row)
    session.commit()


def disconnect(session: Session, user_id: int) -> None:
    """Revoca el token en COROS (si se puede) y borra la conexión."""
    row = session.get(CorosOAuth, user_id)
    if row is None:
        return
    try:
        meta = discover()
        if meta.get("revocation_endpoint") and row.refresh_token_enc:
            with _http() as http:
                http.post(meta["revocation_endpoint"], data={
                    "token": decrypt_secret(row.refresh_token_enc), "token_type_hint": "refresh_token",
                    "client_id": row.client_id,
                })  # fmt: skip
    except Exception:  # noqa: BLE001 - desconectar nunca falla por la revocación
        logger.info("COROS: no se pudo revocar el token")
    session.delete(row)
    session.commit()


# ─── Herramientas MCP ────────────────────────────────────────────────────────


def _parse(res: httpx.Response) -> dict:
    """Respuesta JSON-RPC, venga como JSON o como evento SSE (`data: {...}`)."""
    if "text/event-stream" in res.headers.get("content-type", ""):
        for line in res.text.splitlines():
            if line.startswith("data:") and (data := line[5:].strip()):
                msg = json.loads(data)
                if "result" in msg or "error" in msg:
                    return msg
        return {}
    return res.json() if res.content else {}


class CorosMcp:
    """Cliente de las herramientas del MCP oficial de COROS para una persona (renueva el token solo)."""

    def __init__(self, session: Session, user_id: int) -> None:
        row = session.get(CorosOAuth, user_id)
        if row is None or row.status == "expired":
            raise CorosOAuthError("Conecta COROS (conexión oficial) en Ajustes → Conexiones.")
        self.session, self.row = session, row
        self._id = 0

    def _token(self) -> str:
        if self.row.expires_at and self.row.expires_at - timedelta(minutes=2) <= datetime.now(UTC):
            _refresh(self.session, self.row)
        return decrypt_secret(self.row.access_token_enc)

    def _rpc(self, method: str, params: dict | None = None, retry: bool = True) -> Any:
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        headers = {"Authorization": f"Bearer {self._token()}", "Accept": "application/json, text/event-stream"}
        with _http() as http:
            res = http.post(self.row.mcp_url, json=body, headers=headers)
        if res.status_code == 401 and retry:
            _refresh(self.session, self.row)
            return self._rpc(method, params, retry=False)
        if res.status_code >= 400:
            logger.warning("COROS MCP: %s respondió %s", method, res.status_code)
            raise CorosOAuthError("COROS no está disponible ahora mismo. Inténtalo más tarde.")
        msg = _parse(res)
        if "error" in msg:
            raise CorosOAuthError(str(msg["error"].get("message") or "COROS devolvió un error.")[:255])
        return msg.get("result", {})

    def list_tools(self) -> list[dict]:
        return self._rpc("tools/list").get("tools", [])

    def call_raw(self, name: str, arguments: dict) -> dict:
        """Resultado MCP tal cual (`content` con textos, recursos o enlaces); error si `isError`."""
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
            raise CorosOAuthError((" ".join(texts) or "COROS rechazó la petición.")[:255])
        return result

    def call(self, name: str, arguments: dict) -> Any:
        """Llama a una herramienta y devuelve su resultado (el texto JSON ya interpretado si lo es)."""
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        if result.get("isError"):
            raise CorosOAuthError((" ".join(texts) or "COROS rechazó la petición.")[:255])
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        joined = "\n".join(texts)
        try:
            return json.loads(joined)
        except ValueError:
            return joined
