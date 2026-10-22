"""Notificaciones en el móvil: suscribir el dispositivo, preferencias por tipo y aviso de prueba."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from app.api.deps import CurrentUser, SessionDep
from app.core.rate_limit import limiter
from app.services import notifications as svc

router = APIRouter(prefix="/notifications", tags=["notificaciones"])


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=256)
    auth: str = Field(min_length=8, max_length=64)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=2048)
    keys: SubscriptionKeys
    user_agent: str = Field(default="", max_length=500)
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("endpoint")
    @classmethod
    def push_service(cls, value: str) -> str:
        if not svc.allowed_endpoint(value):
            raise ValueError("El navegador devolvió un servicio de notificaciones no admitido.")
        return value


class EndpointIn(BaseModel):
    endpoint: str = Field(max_length=2048)


class PrefsIn(BaseModel):
    daily_session: bool
    daily_hour: int = Field(ge=0, le=23)
    timezone: str = Field(max_length=64)
    overload: bool
    sync_error: bool
    achievements: bool
    plan_changes: bool

    @field_validator("timezone")
    @classmethod
    def valid_tz(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Zona horaria no válida.") from exc
        return value


class DeviceOut(BaseModel):
    id: int
    user_agent: str
    created_at: datetime
    last_ok_at: datetime | None
    endpoint_host: str


class SentOut(BaseModel):
    title: str
    kind: str
    sent_at: datetime


class ConfigOut(BaseModel):
    public_key: str = Field(description="Clave VAPID pública (base64url) para PushManager.subscribe")
    prefs: PrefsIn
    devices: list[DeviceOut]
    recent: list[SentOut]


def _config(session: SessionDep, user_id: int) -> ConfigOut:
    _, public = svc.vapid_keys(session)
    prefs = svc.get_prefs(session, user_id)
    return ConfigOut(
        public_key=public,
        prefs=PrefsIn.model_validate(prefs, from_attributes=True),
        devices=[
            DeviceOut(
                id=s.id,
                user_agent=s.user_agent,
                created_at=s.created_at,
                last_ok_at=s.last_ok_at,
                endpoint_host=(s.endpoint.split("/")[2] if "//" in s.endpoint else ""),
            )
            for s in svc.subscriptions(session, user_id)
        ],  # fmt: skip
        recent=[SentOut(title=n.title, kind=n.kind, sent_at=n.sent_at) for n in svc.recent_log(session, user_id)],
    )


@router.get("", summary="Clave pública, preferencias y dispositivos suscritos")
def get_config(session: SessionDep, user: CurrentUser) -> ConfigOut:
    return _config(session, user.id)


@router.post("/subscriptions", summary="Suscribir este dispositivo", status_code=status.HTTP_201_CREATED,
             responses={422: {"description": "Servicio push no admitido"}})  # fmt: skip
def subscribe(body: SubscriptionIn, session: SessionDep, user: CurrentUser) -> ConfigOut:
    svc.subscribe(session, user.id, body.endpoint, body.keys.p256dh, body.keys.auth, body.user_agent)
    if body.timezone:
        prefs = svc.get_prefs(session, user.id)
        try:
            ZoneInfo(body.timezone)
            prefs.timezone = body.timezone
            session.add(prefs)
            session.commit()
        except (ZoneInfoNotFoundError, ValueError):
            pass  # se queda la zona anterior
    return _config(session, user.id)


@router.post("/subscriptions/remove", summary="Dejar de recibir avisos en este dispositivo")
def unsubscribe(body: EndpointIn, session: SessionDep, user: CurrentUser) -> ConfigOut:
    svc.unsubscribe(session, user.id, body.endpoint)
    return _config(session, user.id)


@router.delete("/devices/{device_id}", summary="Quitar un dispositivo", status_code=204,
               responses={404: {"description": "No encontrado"}})  # fmt: skip
def remove_device(device_id: int, session: SessionDep, user: CurrentUser) -> Response:
    sub = next((s for s in svc.subscriptions(session, user.id) if s.id == device_id), None)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispositivo no encontrado.")
    session.delete(sub)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/prefs", summary="Qué avisos recibir y a qué hora")
def update_prefs(body: PrefsIn, session: SessionDep, user: CurrentUser) -> ConfigOut:
    prefs = svc.get_prefs(session, user.id)
    for key, value in body.model_dump().items():
        setattr(prefs, key, value)
    session.add(prefs)
    session.commit()
    return _config(session, user.id)


@router.post("/test", summary="Enviar una notificación de prueba a mis dispositivos",
             responses={409: {"description": "Sin dispositivos suscritos"}})  # fmt: skip
@limiter.limit("5/minute")
def send_test(request: Request, session: SessionDep, user: CurrentUser) -> dict:
    if not svc.subscriptions(session, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Activa primero las notificaciones en este dispositivo.")
    return svc.push(session, user.id, "APP ENTRENOS", "¡Las notificaciones funcionan! 🎉", "/ajustes", tag="test")
