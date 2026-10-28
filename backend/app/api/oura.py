"""Anillo Oura: conexión (OAuth2), sincronización, webhooks, fuente de recuperación y vistas de salud."""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Literal
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.api.sources import _allowed_origin
from app.core.rate_limit import limiter
from app.models import (
    CorosCredential,
    CorosOAuth,
    DailyMetric,
    GarminCredential,
    IngestToken,
    OuraConnection,
)
from app.services import daily_sources, health_views, oura_config, oura_oauth, oura_webhooks
from app.services.mailer import link
from app.services.oura_sync import oura_enabled
from app.services.sync_schedule import get_user_settings

logger = logging.getLogger(__name__)


def require_oura(session: SessionDep, user: CurrentUser) -> None:
    """404 `MODULE_DISABLED` si la cuenta no puede usar Oura (ver `oura_sync.oura_enabled`)."""
    if not oura_enabled(session, user):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "El módulo «Oura Ring» está desactivado por el administrador.",
            headers={"X-Error-Code": "MODULE_DISABLED"},
        )


_OURA = [Depends(require_oura)]
router = APIRouter(tags=["oura"], dependencies=_OURA)
# Sin sesión: la vuelta de la autorización la abre el navegador y los webhooks los llama Oura.
public_router = APIRouter(tags=["oura"])
# Vistas de salud: sirven para cualquier fuente (sin Oura, con lo del reloj).
health_router = APIRouter(prefix="/health", tags=["salud"])

RecoverySource = Literal["auto", "watch", "oura"]
MAX_RANGE_DAYS = 400


class RingOut(BaseModel):
    model: str | None = None
    color: str | None = None
    size: int | None = None
    firmware: str | None = None
    battery_level: int | None = None
    battery_at: datetime | None = None


class HistoryOut(BaseModel):
    status: Literal["idle", "running", "done", "error"]
    from_: date | None = Field(default=None, serialization_alias="from")
    to: date | None = None


class OuraStatusOut(BaseModel):
    configured: bool = Field(description="El servidor tiene la app de Oura configurada")
    connected: bool
    status: Literal["ok", "expired", "error"] | None
    last_sync_at: datetime | None
    last_error: str | None
    scopes: list[str]
    ring: RingOut | None
    recovery_source: RecoverySource
    has_watch: bool = Field(description="Hay un reloj conectado o con datos recientes")
    history: HistoryOut


class RecoverySourceIn(BaseModel):
    source: RecoverySource


class RecoverySourceOut(BaseModel):
    recovery_source: RecoverySource


def _has_watch(session: SessionDep, user_id: int) -> bool:
    if any(session.get(m, user_id) is not None for m in (GarminCredential, CorosCredential, CorosOAuth, IngestToken)):
        return True
    rows = session.exec(
        select(DailyMetric).where(DailyMetric.user_id == user_id, DailyMetric.day >= date.today() - timedelta(days=60))
    ).all()
    return any(set(daily_sources.by_source(r)) & set(daily_sources.WATCH_SOURCES) for r in rows)


def _status(session: SessionDep, user_id: int) -> OuraStatusOut:
    conn = session.get(OuraConnection, user_id)
    ring = None
    if conn is not None and conn.ring:
        r = conn.ring
        ring = RingOut(
            model=r.get("model"), color=r.get("color"), size=r.get("size") if isinstance(r.get("size"), int) else None,
            firmware=r.get("firmware"), battery_level=r.get("battery_level"), battery_at=r.get("battery_at"),
        )  # fmt: skip
    pref = get_user_settings(session, user_id).recovery_source or "auto"
    return OuraStatusOut(
        configured=oura_config.credentials(session).configured,
        connected=conn is not None,
        status=conn.status if conn else None,
        last_sync_at=conn.last_sync_at if conn else None,
        last_error=(conn.last_error or None) if conn else None,
        scopes=conn.scopes.split() if conn and conn.scopes else [],
        ring=ring,
        recovery_source=pref if pref in ("auto", "watch", "oura") else "auto",
        has_watch=_has_watch(session, user_id),
        history=HistoryOut(status=conn.history_status, from_=conn.history_from, to=conn.history_to)
        if conn
        else HistoryOut(status="idle"),
    )


def _request_origin(request: Request, origin: str | None) -> str:
    """Web desde la que se conecta: `origin` explícito, cabecera Origin, Referer o la URL pública."""
    candidates = [origin, request.headers.get("origin")]
    if referer := request.headers.get("referer"):
        parsed = urlparse(referer)
        candidates.append(f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else None)
    for c in candidates:
        if c and _allowed_origin(request, c.rstrip("/")):
            return c.rstrip("/")
    return link("").rstrip("/")


@router.get(
    "/sources/oura",
    summary="Estado de la conexión con Oura",
    description="Si el servidor la tiene configurada, si está conectada, anillo y batería, fuente de recuperación "
    "elegida, si hay reloj y el estado de la importación del histórico.",
    response_model_by_alias=True,
)
def get_oura(session: SessionDep, user: CurrentUser) -> OuraStatusOut:
    return _status(session, user.id)


@router.get(
    "/sources/oura/connect",
    summary="Empezar la conexión con Oura (devuelve la URL de autorización)",
    description="La vuelta llega a la misma web desde la que se conecta (`origin`, cabecera Origin o Referer).",
    responses={409: {"description": "Oura no está configurado en este servidor"}},
)
@limiter.limit("10/minute")
def oura_connect(request: Request, session: SessionDep, user: CurrentUser, origin: str | None = None) -> dict:
    try:
        return {"url": oura_oauth.start(session, user.id, _request_origin(request, origin))}
    except oura_oauth.OuraOAuthError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@public_router.get(
    "/sources/oura/callback",
    summary="Vuelta de la autorización de Oura (la abre el navegador)",
    include_in_schema=False,
)
def oura_callback(session: SessionDep, state: str = "", code: str = "", error: str = "") -> RedirectResponse:
    pending = oura_oauth.pending_state(session, state)
    origin = pending.redirect_uri.removesuffix(oura_oauth.CALLBACK_PATH) if pending else link("").rstrip("/")
    target = f"{origin}/ajustes"

    def fail(reason: str) -> RedirectResponse:
        return RedirectResponse(f"{target}?oura=error&motivo={quote(reason)}", status_code=status.HTTP_303_SEE_OTHER)

    if error == "invalid_scope" and pending is not None and pending.provider == oura_oauth.PROVIDER:
        # Oura no reconoce algún permiso extra: se repite la autorización solo con los documentados.
        user_id, origin_url = pending.user_id, origin
        session.delete(pending)
        session.commit()
        url = oura_oauth.start(session, user_id, origin_url, basic=True)
        return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
    if error or not code or pending is None:
        if pending is not None:
            session.delete(pending)
            session.commit()
        return fail("cancelada" if error == "access_denied" else "autorizacion")
    if not oura_enabled(session, pending.user_id):
        session.delete(pending)
        session.commit()
        return fail("modulo")
    try:
        oura_oauth.finish(session, state, code)
    except oura_oauth.OuraOAuthError as exc:
        return fail("anillo_en_otra_cuenta" if "otra cuenta" in str(exc) else "autorizacion")
    except Exception:
        logger.exception("Oura: fallo inesperado al terminar la conexión")
        return fail("error")
    return RedirectResponse(f"{target}?oura=ok", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/sources/oura/sync",
    summary="Sincronizar Oura ahora (últimos 3 días)",
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"description": "Oura no está conectado"}},
)
@limiter.limit("6/minute")
def oura_sync_now(request: Request, session: SessionDep, user: CurrentUser) -> dict:
    if session.get(OuraConnection, user.id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Conecta Oura primero.")
    from app.tasks.oura import oura_sync_user_task

    oura_sync_user_task.apply_async(args=[user.id], argsrepr="(usuario)")
    return {"queued": True}


@router.delete(
    "/sources/oura",
    summary="Desconectar Oura",
    description="Con `purge=true` borra además todo lo que vino de Oura (series, sesiones, etiquetas, modo "
    "descanso, sus valores en las métricas diarias y los entrenos importados de Oura).",
    status_code=204,
)
def oura_disconnect(session: SessionDep, user: CurrentUser, purge: bool = False) -> Response:
    oura_oauth.disconnect(session, user.id, purge=purge)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/settings/recovery-source",
    summary="Fuente del sueño y la recuperación",
    description="`auto` (Oura si está conectado), `watch` (el reloj) u `oura`. Recalcula los últimos 365 días.",
    responses={422: {"description": "Fuente no válida"}},
)
def put_recovery_source(body: RecoverySourceIn, session: SessionDep, user: CurrentUser) -> RecoverySourceOut:
    settings = get_user_settings(session, user.id)
    settings.recovery_source = body.source
    session.add(settings)
    session.commit()
    daily_sources.recompute_user(session, user.id)
    return RecoverySourceOut(recovery_source=body.source)


# ─── Webhooks (los llama Oura) ───────────────────────────────────────────────


@public_router.get(
    "/sources/oura/webhook",
    summary="Verificación de la URL de webhooks de Oura",
    responses={401: {"description": "Token de verificación incorrecto"}},
)
def oura_webhook_verify(verification_token: str = "", challenge: str = "") -> dict:
    if not oura_webhooks.valid_verification(verification_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de verificación no válido.")
    return {"challenge": challenge}


@public_router.post(
    "/sources/oura/webhook",
    summary="Aviso de Oura: un dato nuevo, cambiado o borrado",
    description="Firma `x-oura-signature` (HMAC-SHA256 del secreto de la app sobre `x-oura-timestamp` + cuerpo) "
    "y aviso de menos de 5 minutos. Se encola la descarga y se responde enseguida.",
    responses={401: {"description": "Firma no válida o aviso caducado"}},
)
@limiter.limit("600/minute")
async def oura_webhook(request: Request, session: SessionDep) -> dict:
    body = await request.body()
    if len(body) > 100_000 or not oura_webhooks.valid_signature(
        body, request.headers.get("x-oura-signature"), request.headers.get("x-oura-timestamp")
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Firma no válida.")
    try:
        event = json.loads(body)
    except ValueError:
        return {"ok": False}
    if not isinstance(event, dict):
        return {"ok": False}
    oura_user = str(event.get("user_id") or "")
    conn = (
        session.exec(select(OuraConnection).where(OuraConnection.oura_user_id == oura_user)).first()
        if oura_user
        else None
    )
    data_type, object_id = str(event.get("data_type") or ""), str(event.get("object_id") or "")
    if conn is None or not object_id or not oura_enabled(session, conn.user_id):
        return {"ok": True}
    from app.tasks.oura import oura_fetch_object_task

    try:
        oura_fetch_object_task.apply_async(
            args=[conn.user_id, data_type[:40], object_id[:120], str(event.get("event_type") or "update")[:16]],
            argsrepr="(usuario, tipo, id, evento)",
        )
    except Exception:  # noqa: BLE001 - la sincronización periódica lo traerá igualmente
        logger.warning("No se pudo encolar un aviso de Oura")
    return {"ok": True}


# ─── Vistas de salud ─────────────────────────────────────────────────────────


@health_router.get(
    "/night/{day}",
    summary="Detalle de una noche",
    description="Fases, siestas, hipnograma (1 profundo, 2 ligero, 3 REM, 4 despierto, cada 5 min), FC y HRV "
    "nocturnas, puntuaciones, preparación, hora óptima de dormir, SpO2 y etiquetas. Fuente: la elegida.",
)
def get_night(day: date, session: SessionDep, user: CurrentUser) -> dict:
    return health_views.night(session, user, day)


@health_router.get(
    "/day/{day}",
    summary="Detalle de un día",
    description="FC continua [[epoch_s, ppm, origen]], actividad, estrés, resiliencia, sesiones, etiquetas y "
    "modo descanso.",
)
def get_day(day: date, session: SessionDep, user: CurrentUser) -> dict:
    return health_views.day_view(session, user, day)


@health_router.get(
    "/rest-periods",
    summary="Periodos de modo descanso",
    responses={422: {"description": "Rango no válido"}},
)
def get_rest_periods(
    session: SessionDep,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    date_to = date_to or date.today()
    date_from = date_from or date_to - timedelta(days=90)
    if date_to < date_from or (date_to - date_from).days > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Rango de fechas no válido (máx. 400 días).")
    return health_views.rest_periods(session, user, date_from, date_to)
