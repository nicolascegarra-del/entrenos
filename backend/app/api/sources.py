"""Otros relojes: importar FIT/GPX/TCX, conectar COROS y recibir datos de Health Connect."""

import base64
import binascii
import logging
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.core.rate_limit import limiter
from app.models import CorosCredential, CorosOAuth, IngestToken
from app.services import apple_health, coros, coros_oauth, health_connect
from app.services.file_import import FileImportError, after_import, parse_file, save_imported
from app.services.mailer import link

logger = logging.getLogger(__name__)

router = APIRouter(tags=["otros relojes"])

MAX_B64 = 34_000_000  # ~25 MB de fichero


class FileIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_b64: str = Field(min_length=8, max_length=MAX_B64)


class ImportOut(BaseModel):
    activity_id: int
    created: bool
    source: str


class CorosIn(BaseModel):
    account: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class CorosOut(BaseModel):
    account: str
    status: str
    last_sync_at: datetime | None
    last_error: str


class CorosOfficialOut(BaseModel):
    status: str
    connected_at: datetime
    last_sync_at: datetime | None = None
    last_error: str


class ConnectIn(BaseModel):
    origin: str = Field(min_length=8, max_length=200, description="Web desde la que se conecta (para volver a ella)")


class IngestOut(BaseModel):
    hint: str
    created_at: datetime
    last_used_at: datetime | None


class SourcesOut(BaseModel):
    coros: CorosOut | None
    coros_official: CorosOfficialOut | None = None
    health_connect: IngestOut | None
    ingest_url: str = Field(description="URL para la app de Health Connect")
    apple_shortcut_url: str = Field(description="URL para el Atajo de iOS (Apple Watch)")
    apple_last_at: datetime | None = Field(description="Último entreno llegado de Apple")


def _sources(session: SessionDep, user_id: int) -> SourcesOut:
    cred = session.get(CorosCredential, user_id)
    token = session.get(IngestToken, user_id)
    official = session.get(CorosOAuth, user_id)
    return SourcesOut(
        coros=CorosOut.model_validate(cred, from_attributes=True) if cred else None,
        coros_official=CorosOfficialOut.model_validate(official, from_attributes=True) if official else None,
        health_connect=IngestOut.model_validate(token, from_attributes=True) if token else None,
        ingest_url=link("/api/v1/ingest/health-connect"),  # URL pública (Admin → Correo), como los emails
        apple_shortcut_url=link("/api/v1/ingest/apple-shortcuts"),
        apple_last_at=last.start_time if (last := apple_health.latest_import_activity(session, user_id)) else None,
    )


@router.post(
    "/imports/file",
    summary="Importar una actividad desde un fichero FIT, GPX o TCX",
    responses={422: {"description": "Fichero no válido"}},
)
@limiter.limit("30/minute")
def import_file(request: Request, body: FileIn, session: SessionDep, user: CurrentUser) -> ImportOut:
    try:
        data = base64.b64decode(body.content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "El fichero no llegó bien. Vuelve a subirlo."
        ) from exc
    try:
        act, kind = parse_file(body.filename, data)
    except FileImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if not act.name:
        act.name = body.filename.rsplit(".", 1)[0][:255]
    activity, created = save_imported(session, user.id, act, kind, respect_deleted=False)
    if created:
        after_import(session, user.id)
    return ImportOut(activity_id=activity.id, created=created, source=activity.source)


@router.get("/sources", summary="Estado de COROS y Health Connect")
def get_sources(session: SessionDep, user: CurrentUser) -> SourcesOut:
    return _sources(session, user.id)


@router.post(
    "/sources/coros",
    summary="Conectar COROS (la contraseña no se guarda)",
    responses={400: {"description": "COROS rechazó las credenciales"}},
)
@limiter.limit("5/minute")
def connect_coros(request: Request, body: CorosIn, session: SessionDep, user: CurrentUser) -> SourcesOut:
    try:
        coros.connect(session, user.id, body.account.strip(), body.password)
    except coros.CorosError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    from app.tasks.sources import coros_sync_task

    coros_sync_task.apply_async(args=[user.id], argsrepr="(usuario)")
    return _sources(session, user.id)


@router.post("/sources/coros/sync", summary="Sincronizar COROS ahora", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("6/minute")
def sync_coros(request: Request, session: SessionDep, user: CurrentUser) -> dict:
    if session.get(CorosCredential, user.id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Conecta primero tu cuenta de COROS.")
    from app.tasks.sources import coros_sync_task

    coros_sync_task.apply_async(args=[user.id], argsrepr="(usuario)")
    return {"queued": True}


@router.delete("/sources/coros", summary="Desconectar COROS", status_code=204)
def disconnect_coros(session: SessionDep, user: CurrentUser) -> Response:
    cred = session.get(CorosCredential, user.id)
    if cred is not None:
        session.delete(cred)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sources/health-connect/token", summary="Crear (o renovar) el token de Health Connect")
def new_ingest_token(session: SessionDep, user: CurrentUser) -> dict:
    return {"token": health_connect.create_token(session, user.id), **_sources(session, user.id).model_dump()}


@router.delete("/sources/health-connect/token", summary="Revocar el token de Health Connect", status_code=204)
def revoke_ingest_token(session: SessionDep, user: CurrentUser) -> Response:
    row = session.get(IngestToken, user.id)
    if row is not None:
        session.delete(row)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/ingest/health-connect",
    summary="Recibir datos de Health Connect (webhook de la app Android)",
    description="Autenticación con la cabecera `X-Api-Key: <token personal>` (Ajustes → Otros relojes).",
    responses={401: {"description": "Token no válido"}},
)
@limiter.limit("60/minute")
async def ingest_health_connect(
    request: Request, session: SessionDep, x_api_key: str | None = Header(default=None)
) -> dict:
    user_id = health_connect.user_for_token(session, x_api_key)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de Health Connect no válido.")
    if int(request.headers.get("content-length") or 0) > 10_000_000:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Envío demasiado grande.")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "El cuerpo no es JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Formato no reconocido.")
    return health_connect.ingest(session, user_id, payload)


# ─── COROS oficial (OAuth del MCP de COROS): enviar entrenos al calendario ───


def _allowed_origin(request: Request, origin: str) -> bool:
    """
    Solo se vuelve a la propia web: localhost/127.0.0.1 (desarrollo, también por http), la URL pública
    (Admin → Correo) o, por https, el host que sirve la petición (p. ej. un túnel).
    """
    parsed = urlparse(origin)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path not in ("", "/"):
        return False
    host = parsed.hostname
    if host in ("localhost", "127.0.0.1") or host == urlparse(link("/")).hostname:
        return True
    served = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(":")[0]
    return parsed.scheme == "https" and host == served


@router.post(
    "/sources/coros-official/connect",
    summary="Empezar la conexión oficial con COROS (devuelve la URL de autorización)",
    responses={400: {"description": "Origen no permitido"}, 502: {"description": "COROS no disponible"}},
)
@limiter.limit("10/minute")
def coros_official_connect(request: Request, body: ConnectIn, session: SessionDep, user: CurrentUser) -> dict:
    if not _allowed_origin(request, body.origin):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Origen no permitido.")
    try:
        return {"url": coros_oauth.start(session, user.id, body.origin)}
    except coros_oauth.CorosOAuthError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except Exception as exc:  # red, JSON inesperado…
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "COROS no está disponible ahora mismo.") from exc


@router.get(
    "/sources/coros-official/callback",
    summary="Vuelta de la autorización de COROS (la abre el navegador)",
    include_in_schema=False,
)
def coros_official_callback(session: SessionDep, state: str = "", code: str = "", error: str = "") -> RedirectResponse:
    from app.models import OAuthState

    pending = session.get(OAuthState, state) if state else None
    origin = pending.redirect_uri.removesuffix(coros_oauth.CALLBACK_PATH) if pending else link("").rstrip("/")
    target = f"{origin}/ajustes/conexiones"
    if error or not code or pending is None:
        if pending is not None:
            session.delete(pending)
            session.commit()
        reason = "cancelada" if error == "access_denied" else "error"
        return RedirectResponse(f"{target}?coros={reason}", status_code=status.HTTP_303_SEE_OTHER)
    try:
        coros_oauth.finish(session, state, code)
    except coros_oauth.CorosOAuthError:
        return RedirectResponse(f"{target}?coros=error", status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        return RedirectResponse(f"{target}?coros=error", status_code=status.HTTP_303_SEE_OTHER)
    from app.tasks.sources import coros_official_sync_task

    try:
        from app.services.coros_official import FIRST_SYNC_DAYS

        coros_official_sync_task.apply_async(args=[pending.user_id, FIRST_SYNC_DAYS], argsrepr="(usuario, días)")
    except Exception:  # noqa: BLE001 - se sincronizará en la siguiente pasada
        logger.warning("No se pudo encolar la primera sincronización de COROS")
    return RedirectResponse(f"{target}?coros=ok", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/sources/coros-official/sync",
    summary="Traer ahora las actividades de COROS (conexión oficial)",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("6/minute")
def coros_official_sync(request: Request, session: SessionDep, user: CurrentUser) -> dict:
    if session.get(CorosOAuth, user.id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Conecta COROS primero.")
    from app.services.coros_official import FIRST_SYNC_DAYS
    from app.tasks.sources import coros_official_sync_task

    coros_official_sync_task.apply_async(args=[user.id, FIRST_SYNC_DAYS], argsrepr="(usuario, días)")
    return {"queued": True}


@router.delete("/sources/coros-official", summary="Desconectar la conexión oficial de COROS", status_code=204)
def coros_official_disconnect(session: SessionDep, user: CurrentUser) -> Response:
    coros_oauth.disconnect(session, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
