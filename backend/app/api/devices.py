"""Relojes y pulseras por la cuenta de su marca (no oficial): Suunto, Amazfit (Zepp) y Xiaomi (Mi Fitness)."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.core.rate_limit import limiter
from app.services import devices, modules
from app.services.devices import xiaomi

router = APIRouter(tags=["otros relojes"])

Provider = Literal["suunto", "zepp", "xiaomi"]
PasswordProvider = Literal["suunto", "zepp"]


class DeviceOut(BaseModel):
    provider: str
    label: str
    account: str
    status: str = Field(description="ok | expired | error | pending (esperando a que se apruebe el QR)")
    last_sync_at: datetime | None
    last_error: str


class DevicesOut(BaseModel):
    enabled: list[str] = Field(description="Marcas activadas para tu cuenta")
    connections: list[DeviceOut]


class CredentialsIn(BaseModel):
    account: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class QrIn(BaseModel):
    region: Literal[xiaomi.REGIONS] = xiaomi.DEFAULT_REGION  # type: ignore[valid-type]


class QrOut(BaseModel):
    login_url: str = Field(description="Enlace a abrir en el móvil (o a codificar como QR)")
    qr: str = Field(description="Imagen del QR que da Xiaomi")


def _check(session: SessionDep, user: CurrentUser, provider: str) -> None:
    if not modules.enabled(session, provider, user):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"El módulo «{modules.LABELS[provider]}» está desactivado por el administrador.",
            headers={"X-Error-Code": "MODULE_DISABLED"},
        )


def _status(session: SessionDep, user: CurrentUser) -> DevicesOut:
    labels = {k: p.label for k, p in devices.providers().items()}
    on = [k for k in labels if modules.enabled(session, k, user)]
    rows = [devices.get_connection(session, user.id, k) for k in on]
    return DevicesOut(enabled=on, connections=[
        DeviceOut(provider=c.provider, label=labels[c.provider], account=c.account, status=c.status,
                  last_sync_at=c.last_sync_at, last_error=c.last_error)
        for c in rows if c is not None
    ])  # fmt: skip


def _queue_sync(user_id: int, provider: str) -> None:
    from app.tasks.devices import device_sync_task

    device_sync_task.apply_async(args=[user_id, provider], argsrepr="(usuario, marca)")


@router.get("/sources/devices", summary="Estado de Suunto, Amazfit y Xiaomi")
def get_devices(session: SessionDep, user: CurrentUser) -> DevicesOut:
    return _status(session, user)


@router.post(
    "/sources/devices/xiaomi/qr",
    summary="Empezar a conectar Xiaomi con un QR",
    description=(
        "Devuelve el QR para aprobar el inicio de sesión desde la app de Xiaomi del móvil. La conexión queda "
        "en `pending` hasta que se aprueba (unos 2 minutos como máximo); luego pasa a `ok` y se importan los "
        "entrenos."
    ),
    responses={400: {"description": "Xiaomi no respondió"}, 404: {"description": "Módulo desactivado"}},
)
@limiter.limit("6/minute")
def xiaomi_qr(request: Request, body: QrIn, session: SessionDep, user: CurrentUser) -> QrOut:
    _check(session, user, "xiaomi")
    try:
        pending = xiaomi.start_qr()
    except devices.DeviceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    devices.save_session(session, user.id, "xiaomi", {**pending, "region": body.region}, "", status="pending")
    from app.tasks.devices import xiaomi_wait_qr_task

    xiaomi_wait_qr_task.apply_async(args=[user.id], argsrepr="(usuario)")
    return QrOut(login_url=pending["login_url"], qr=pending["qr"])


@router.post(
    "/sources/devices/{provider}",
    summary="Conectar Suunto o Amazfit con email y contraseña (la contraseña no se guarda)",
    responses={400: {"description": "La marca rechazó las credenciales"}, 404: {"description": "Desactivado"}},
)
@limiter.limit("5/minute")
def connect_device(
    request: Request, provider: PasswordProvider, body: CredentialsIn, session: SessionDep, user: CurrentUser
) -> DevicesOut:
    _check(session, user, provider)
    try:
        devices.connect(session, user.id, provider, body.account.strip(), body.password)
    except devices.DeviceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _queue_sync(user.id, provider)
    return _status(session, user)


@router.post("/sources/devices/{provider}/sync", summary="Sincronizar ahora", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("6/minute")
def sync_device(request: Request, provider: Provider, session: SessionDep, user: CurrentUser) -> dict:
    _check(session, user, provider)
    conn = devices.get_connection(session, user.id, provider)
    if conn is None or conn.status == "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Conecta primero la cuenta.")
    _queue_sync(user.id, provider)
    return {"queued": True}


@router.delete("/sources/devices/{provider}", summary="Desconectar (los entrenos ya traídos se quedan)",
               status_code=204)  # fmt: skip
def disconnect_device(provider: Provider, session: SessionDep, user: CurrentUser) -> Response:
    devices.disconnect(session, user.id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
