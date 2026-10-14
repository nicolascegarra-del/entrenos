from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep
from app.core.rate_limit import limiter
from app.models import GarminCredential, MetricDefinition, SyncRun
from app.schemas.activity import MetricDefinitionRead, SyncRunRead
from app.services.garmin_client import disconnect, has_tokens
from app.tasks import garmin_connect as gc
from app.tasks.sync import sync_user_task

router = APIRouter(tags=["garmin"])


class GarminConnection(BaseModel):
    status: str  # none | ok | expired
    display_name: str | None
    connected_at: datetime | None
    last_ok_at: datetime | None


class GarminStatusOut(BaseModel):
    connected: bool
    connection: GarminConnection
    last_run: SyncRunRead | None


class ConnectIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class MfaIn(BaseModel):
    code: str = Field(pattern=r"^\d{4,8}$")


class ConnectState(BaseModel):
    status: str  # pending | needs_mfa | verifying | connected | error
    error: str | None


@router.get("/garmin/status", summary="Estado de la conexión y última sincronización")
def garmin_status(session: SessionDep, user: CurrentUser) -> GarminStatusOut:
    connected = has_tokens(user.id)  # migra tokens antiguos en fichero si los hay
    credential = session.get(GarminCredential, user.id)
    last = session.exec(
        select(SyncRun).where(SyncRun.user_id == user.id).order_by(col(SyncRun.started_at).desc())
    ).first()
    return GarminStatusOut(
        connected=connected,
        connection=GarminConnection(
            status=credential.status if credential else "none",
            display_name=credential.display_name if credential else None,
            connected_at=credential.connected_at if credential else None,
            last_ok_at=credential.last_ok_at if credential else None,
        ),
        last_run=SyncRunRead.model_validate(last, from_attributes=True) if last else None,
    )


@router.post(
    "/garmin/connect",
    summary="Conectar Garmin (inicia el login)",
    description=(
        "Inicia el login con Garmin en segundo plano. La contraseña viaja cifrada, se usa una vez y se descarta: "
        "solo se guardan los tokens de sesión cifrados. Consulta el estado con `GET /garmin/connect/{id}`; si "
        "pide código, envíalo con `POST /garmin/connect/{id}/mfa`."
    ),
    status_code=status.HTTP_202_ACCEPTED,
    responses={429: {"description": "Demasiados intentos."}},
)
@limiter.limit("5/15minutes")
def garmin_connect(request: Request, body: ConnectIn, user: CurrentUser) -> dict:
    return {"connect_id": gc.start_connect(user.id, body.email.strip(), body.password)}


def _own_state(connect_id: str, user_id: int) -> dict[str, str]:
    state = gc.get_state(connect_id)
    if not state or state.get("user_id") != str(user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proceso de conexión no encontrado o caducado.")
    return state


@router.get("/garmin/connect/{connect_id}", summary="Estado del proceso de conexión")
def garmin_connect_state(connect_id: str, user: CurrentUser) -> ConnectState:
    state = _own_state(connect_id, user.id)
    return ConnectState(status=state.get("status", gc.PENDING), error=state.get("error") or None)


@router.post(
    "/garmin/connect/{connect_id}/mfa",
    summary="Enviar el código de verificación de Garmin",
    responses={409: {"description": "Este proceso no está esperando un código."}},
)
@limiter.limit("10/15minutes")
def garmin_connect_mfa(request: Request, connect_id: str, body: MfaIn, user: CurrentUser) -> ConnectState:
    state = _own_state(connect_id, user.id)
    if state.get("status") != gc.NEEDS_MFA:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este proceso no está esperando un código.")
    gc.submit_mfa_code(connect_id, body.code)
    return ConnectState(status=gc.VERIFYING, error=None)


@router.delete("/garmin/connection", summary="Desconectar Garmin (borra los tokens)", status_code=204)
def garmin_disconnect(session: SessionDep, user: CurrentUser) -> Response:
    disconnect(session, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/garmin/sync",
    summary="Sincronizar ahora",
    description="Encola una sincronización en segundo plano. Consulta `/garmin/status` para ver el resultado.",
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"description": "Garmin no está conectado."}},
)
def garmin_sync(user: CurrentUser) -> dict:
    if not has_tokens(user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Garmin no está conectado.")
    sync_user_task.delay(user.id)
    return {"queued": True}


@router.get("/metrics/catalog", summary="Catálogo de métricas conocidas")
def metric_catalog(session: SessionDep, _: CurrentUser) -> list[MetricDefinitionRead]:
    rows = session.exec(select(MetricDefinition).order_by(MetricDefinition.key)).all()
    return [MetricDefinitionRead.model_validate(r, from_attributes=True) for r in rows]
