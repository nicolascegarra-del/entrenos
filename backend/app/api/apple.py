"""
Apple Watch: subir el `export.zip` de Apple Salud a trozos y recibir los envíos del Atajo de iOS.

El export puede pesar cientos de MB, así que se sube en trozos binarios (`PUT ...?offset=`): sin
multipart, con progreso real en el navegador y pudiendo reanudar si se corta la conexión.
"""

import secrets
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models import AppleImport
from app.models.base import utcnow
from app.services import apple_health, health_connect

router = APIRouter(tags=["otros relojes"])

MAX_EXPORT_BYTES = 4_000_000_000
CHUNK_BYTES = 8 * 1024 * 1024
MAX_CHUNK_BYTES = 16 * 1024 * 1024
ACTIVE = ("uploading", "queued", "processing")


class AppleImportIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0, le=MAX_EXPORT_BYTES)


class AppleImportOut(BaseModel):
    id: str
    filename: str
    size_bytes: int
    received_bytes: int
    status: str
    progress: int
    result: dict
    error: str
    created_at: datetime
    chunk_bytes: int = CHUNK_BYTES


def upload_path(import_id: str) -> Path:
    folder = Path(get_settings().storage_dir) / "apple"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{import_id}.upload"


def _out(row: AppleImport) -> AppleImportOut:
    return AppleImportOut.model_validate(row, from_attributes=True)


def _own(session: SessionDep, user_id: int, import_id: str) -> AppleImport:
    row = session.get(AppleImport, import_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Importación no encontrada.")
    return row


@router.post("/imports/apple-health", summary="Empezar a subir el export de Apple Salud")
@limiter.limit("10/minute")
def start_apple_import(request: Request, body: AppleImportIn, session: SessionDep, user: CurrentUser) -> AppleImportOut:
    # Una sola subida a la vez: la anterior sin terminar se descarta.
    for old in session.exec(
        select(AppleImport).where(AppleImport.user_id == user.id, AppleImport.status == "uploading")
    ).all():
        upload_path(old.id).unlink(missing_ok=True)
        session.delete(old)
    row = AppleImport(id=secrets.token_hex(16), user_id=user.id, filename=body.filename, size_bytes=body.size_bytes)
    session.add(row)
    session.commit()
    upload_path(row.id).write_bytes(b"")
    return _out(row)


@router.put(
    "/imports/apple-health/{import_id}",
    summary="Subir un trozo del export (cuerpo binario)",
    responses={409: {"description": "El trozo no va en ese punto: reanudar desde `received_bytes`"}},
)
@limiter.limit("240/minute")
async def upload_apple_chunk(
    request: Request, import_id: str, session: SessionDep, user: CurrentUser, offset: int = Query(ge=0)
) -> AppleImportOut:
    row = _own(session, user.id, import_id)
    if row.status != "uploading":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta subida ya terminó.")
    if offset != row.received_bytes:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Se esperaba el byte {row.received_bytes}.")
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > MAX_CHUNK_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Trozo demasiado grande.")
    if not data or row.received_bytes + len(data) > row.size_bytes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "El trozo no cuadra con el tamaño del fichero.")
    with upload_path(row.id).open("r+b") as fh:
        fh.seek(offset)
        fh.write(data)
        fh.truncate()
    row.received_bytes += len(data)
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    return _out(row)


@router.post("/imports/apple-health/{import_id}/finish", summary="Terminar la subida y procesar el export")
def finish_apple_import(import_id: str, session: SessionDep, user: CurrentUser) -> AppleImportOut:
    row = _own(session, user.id, import_id)
    if row.status != "uploading":
        return _out(row)
    if row.received_bytes != row.size_bytes:
        raise HTTPException(status.HTTP_409_CONFLICT, "Falta parte del fichero: vuelve a intentarlo.")
    row.status, row.updated_at = "queued", utcnow()
    session.add(row)
    session.commit()
    from app.tasks.sources import apple_import_task

    apple_import_task.apply_async(args=[row.id])
    return _out(row)


@router.get("/imports/apple-health", summary="Última importación de Apple Salud")
def latest_apple_import(session: SessionDep, user: CurrentUser) -> AppleImportOut | None:
    row = session.exec(
        select(AppleImport).where(AppleImport.user_id == user.id).order_by(AppleImport.created_at.desc())  # type: ignore[attr-defined]
    ).first()
    return _out(row) if row else None


@router.delete("/imports/apple-health/{import_id}", summary="Cancelar una subida", status_code=204)
def cancel_apple_import(import_id: str, session: SessionDep, user: CurrentUser) -> Response:
    row = _own(session, user.id, import_id)
    if row.status in ("uploading", "done", "error"):
        upload_path(row.id).unlink(missing_ok=True)
        session.delete(row)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/ingest/apple-shortcuts",
    summary="Recibir entrenos del Atajo de iOS (Apple Watch)",
    description="Autenticación con la cabecera `X-Api-Key: <token personal>` (el mismo que Health Connect).",
    responses={401: {"description": "Token no válido"}},
)
@limiter.limit("60/minute")
async def ingest_apple_shortcut(
    request: Request, session: SessionDep, x_api_key: str | None = Header(default=None)
) -> dict:
    user_id = health_connect.user_for_token(session, x_api_key)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token no válido: cópialo de Ajustes → Conexiones.")
    if int(request.headers.get("content-length") or 0) > 10_000_000:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Envío demasiado grande.")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "El cuerpo no es JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Formato no reconocido.")
    return apple_health.ingest_shortcut(session, user_id, payload)
