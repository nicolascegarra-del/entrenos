"""Otros relojes: importar FIT/GPX/TCX, conectar COROS y recibir datos de Health Connect."""

import base64
import binascii
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.core.rate_limit import limiter
from app.models import CorosCredential, IngestToken
from app.services import coros, health_connect
from app.services.file_import import FileImportError, after_import, parse_file, save_imported
from app.services.mailer import link

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


class IngestOut(BaseModel):
    hint: str
    created_at: datetime
    last_used_at: datetime | None


class SourcesOut(BaseModel):
    coros: CorosOut | None
    health_connect: IngestOut | None
    ingest_url: str = Field(description="URL para la app de Health Connect")


def _sources(session: SessionDep, user_id: int) -> SourcesOut:
    cred = session.get(CorosCredential, user_id)
    token = session.get(IngestToken, user_id)
    return SourcesOut(
        coros=CorosOut.model_validate(cred, from_attributes=True) if cred else None,
        health_connect=IngestOut.model_validate(token, from_attributes=True) if token else None,
        ingest_url=link("/api/v1/ingest/health-connect"),  # URL pública (Admin → Correo), como los emails
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
    activity, created = save_imported(session, user.id, act, kind)
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
