"""
Panel de administración: usuarios (estado, permisos, sesiones, enlaces de contraseña,
aprobación y borrado), invitaciones, modo de registro, auditoría y estado del sistema.
Todo exige ser administrador; cada cambio queda en el registro de auditoría.
"""

import json
import logging
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

import redis
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session, col, func, select

from app.api.deps import SessionDep
from app.api.modules import ModulesIn, ModulesOut
from app.api.users import AdminUser
from app.core.config import get_settings
from app.core.crypto import encrypt_secret
from app.core.email import PANEL_KEY, Email, current_config, email_enabled, panel_config, send_email, smtp_error_text
from app.core.rate_limit import limiter
from app.models import (
    AccountTier,
    Activity,
    AppSetting,
    AuditLog,
    ChatConversation,
    ChatMessage,
    GarminCredential,
    Invitation,
    SyncRun,
    User,
    UserStatus,
)
from app.schemas.auth import EMAIL_PATTERN
from app.services import accounts, mailer, modules
from app.services.limits import basic_limits, save_basic_limits
from app.services.signup_guard import captcha_enabled, extra_domains, parse_domains
from app.tasks.heartbeat import HEARTBEAT_KEY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["administración"])

_NOT_FOUND = {404: {"description": "No encontrado"}}
WORKER_STALE_MIN = 3


# ─── Esquemas ────────────────────────────────────────────────────────────────


class SyncBrief(BaseModel):
    at: datetime
    status: str
    error: str | None


class AdminUserRow(BaseModel):
    id: int
    email: str
    is_admin: bool
    status: UserStatus
    tier: AccountTier
    inactivity_warned_at: datetime | None
    locked: bool
    created_at: datetime
    last_login_at: datetime | None
    garmin: str  # none | ok | expired
    last_sync: SyncBrief | None
    activities: int
    ai_questions_30d: int
    ai_tokens_30d: int
    # Módulos fijados para esta cuenta (lo que no aparece sigue el valor general).
    modules: dict[str, bool] = {}


class UsersPage(BaseModel):
    items: list[AdminUserRow]
    total: int


class UserPatch(BaseModel):
    is_admin: bool | None = None
    status: Literal["active", "disabled"] | None = None
    tier: AccountTier | None = None
    # Módulos de esta cuenta: true/false los fija; null la devuelve al valor general.
    modules: dict[str, bool | None] | None = None


class ResetLinkIn(BaseModel):
    send_email: bool = False


class LinkOut(BaseModel):
    link: str
    expires_at: datetime
    emailed: bool


class InvitationIn(BaseModel):
    email: str = Field(max_length=255, pattern=EMAIL_PATTERN)
    days: int = Field(default=7, ge=1, le=30)
    send_email: bool = False


class RenewIn(BaseModel):
    days: int = Field(default=7, ge=1, le=30)
    send_email: bool = False


class InvitationRow(BaseModel):
    id: int
    email: str
    status: Literal["pending", "used", "expired"]
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    used_by_email: str | None


class InvitationCreated(InvitationRow):
    link: str
    emailed: bool


class BasicLimitsIO(BaseModel):
    basic_history_days: int = Field(ge=30, le=3650)
    basic_max_goals: int = Field(ge=1, le=50)
    basic_max_sessions_week: int = Field(ge=1, le=50)


class SettingsOut(BaseModel):
    registration_mode: accounts.RegistrationMode
    email_enabled: bool
    captcha_enabled: bool
    blocked_domains: list[str]  # además de la lista empaquetada de emails desechables
    limits: BasicLimitsIO


class SettingsIn(BaseModel):
    """Todos opcionales: solo se cambia lo que llega."""

    registration_mode: accounts.RegistrationMode | None = None
    blocked_domains: list[str] | None = Field(default=None, max_length=500)
    limits: BasicLimitsIO | None = None


class AuditRow(BaseModel):
    id: int
    created_at: datetime
    actor_email: str | None
    action: str
    target_email: str | None
    detail: dict


class SystemOut(BaseModel):
    inactive_warned: int  # cuentas Básicas avisadas por inactividad
    inactive_deleting_7d: int  # de ellas, las que se borrarán en los próximos 7 días
    worker_ok: bool | None  # None = sin datos (Redis no responde o aún no hay latido)
    last_heartbeat: datetime | None
    last_sync_at: datetime | None
    garmin_expired: list[str]
    sync_failing: list[dict]
    last_backup: dict | None
    email_mode: str
    users_by_status: dict[str, int]
    pending_requests: int


# ─── Utilidades ──────────────────────────────────────────────────────────────


def _get_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    return user


def _rows(session: Session, users: list[User]) -> list[AdminUserRow]:
    """Filas de la tabla con estadísticas, en pocas consultas agrupadas (sin N+1)."""
    ids = [u.id for u in users]
    if not ids:
        return []
    garmin_query = select(GarminCredential.user_id, GarminCredential.status).where(
        col(GarminCredential.user_id).in_(ids)
    )
    garmin = dict(session.exec(garmin_query).all())
    activity_query = (
        select(Activity.user_id, func.count(col(Activity.id)))
        .where(col(Activity.user_id).in_(ids))
        .group_by(Activity.user_id)
    )
    activities = dict(session.exec(activity_query).all())
    since = datetime.now(UTC) - timedelta(days=30)
    usage = {
        uid: (questions, tokens)
        for uid, questions, tokens in session.exec(
            select(
                ChatConversation.user_id,
                func.count(col(ChatMessage.id)).filter(ChatMessage.role == "user"),
                func.coalesce(
                    func.sum(func.coalesce(ChatMessage.input_tokens, 0) + func.coalesce(ChatMessage.output_tokens, 0)),
                    0,
                ),
            )  # fmt: skip
            .join(ChatConversation, col(ChatConversation.id) == col(ChatMessage.conversation_id))
            .where(col(ChatConversation.user_id).in_(ids), ChatMessage.created_at >= since)
            .group_by(ChatConversation.user_id)
        ).all()
    }
    latest = (
        select(SyncRun.user_id, func.max(SyncRun.started_at).label("at"))
        .where(col(SyncRun.user_id).in_(ids))
        .group_by(SyncRun.user_id)
        .subquery()
    )
    syncs = {
        r.user_id: SyncBrief(at=r.started_at, status=r.status, error=r.error)
        for r in session.exec(
            select(SyncRun).join(latest, (SyncRun.user_id == latest.c.user_id) & (SyncRun.started_at == latest.c.at))
        ).all()
    }
    return [
        AdminUserRow(
            id=u.id,
            email=u.email,
            is_admin=u.is_admin,
            tier=u.tier,
            inactivity_warned_at=u.inactivity_warned_at,
            status=u.status,
            locked=accounts.is_locked(u),
            created_at=u.created_at,
            last_login_at=u.last_login_at,
            garmin=garmin.get(u.id, "none"),
            last_sync=syncs.get(u.id),
            activities=activities.get(u.id, 0),
            ai_questions_30d=usage.get(u.id, (0, 0))[0],
            ai_tokens_30d=int(usage.get(u.id, (0, 0))[1]),
            modules=modules.clean_overrides(u.module_overrides),
        )  # fmt: skip
        for u in users
    ]


def _invitation_row(session: Session, inv: Invitation) -> InvitationRow:
    if inv.used_at:
        state = "used"
    elif inv.expires_at < datetime.now(UTC):
        state = "expired"
    else:
        state = "pending"
    used_by = session.get(User, inv.used_by) if inv.used_by else None
    return InvitationRow(id=inv.id, email=inv.email, status=state, created_at=inv.created_at,
                         expires_at=inv.expires_at, used_at=inv.used_at,
                         used_by_email=used_by.email if used_by else None)  # fmt: skip


def _new_invitation_token(inv: Invitation, days: int) -> str:
    token = secrets.token_urlsafe(32)
    inv.token_hash = accounts.token_hash(token)
    inv.expires_at = datetime.now(UTC) + timedelta(days=days)
    return token


# ─── Usuarios ────────────────────────────────────────────────────────────────


@router.get("/users", summary="Usuarios con su estado y uso (paginado)")
def list_users(
    session: SessionDep,
    _: AdminUser,
    q: Annotated[str | None, Query(max_length=100, description="Buscar por email")] = None,
    status_filter: Annotated[UserStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UsersPage:
    query = select(User)
    if q:
        query = query.where(col(User.email).ilike(f"%{q.strip()}%"))
    if status_filter:
        query = query.where(User.status == status_filter)
    total = session.exec(select(func.count()).select_from(query.subquery())).one()
    # Pendientes primero (esperan una decisión), luego por fecha de alta.
    users = session.exec(
        query.order_by((User.status != UserStatus.PENDING), col(User.created_at).desc()).offset(offset).limit(limit)
    ).all()
    return UsersPage(items=_rows(session, list(users)), total=total)


@router.patch(
    "/users/{user_id}",
    summary="Cambiar permisos de administrador o activar/desactivar",
    description="Siempre queda al menos un administrador activo; no puedes desactivarte a ti mismo.",
    responses={**_NOT_FOUND, 409: {"description": "Dejaría la app sin administradores"}},
)
def patch_user(user_id: int, body: UserPatch, session: SessionDep, admin: AdminUser) -> AdminUserRow:
    user = _get_user(session, user_id)
    if user.status == UserStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aprueba o rechaza antes la solicitud de esta persona.")
    if body.status == "disabled" and user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "No puedes desactivar tu propia cuenta.")
    losing_admin = (body.is_admin is False and user.is_admin) or (body.status == "disabled" and user.is_admin)
    if losing_admin and accounts.is_last_admin(session, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Debe quedar al menos un administrador activo.")
    if body.is_admin is not None and body.is_admin != user.is_admin:
        user.is_admin = body.is_admin
        accounts.audit(session, admin, "user.admin_granted" if body.is_admin else "user.admin_revoked", user)
    if body.tier is not None and body.tier != user.tier:
        user.tier = body.tier
        accounts.audit(session, admin, f"user.tier_{body.tier}", user)
    if body.modules:
        try:
            modules.set_user_modules(session, user, body.modules, admin)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if body.status is not None and body.status != user.status:
        user.status = UserStatus(body.status)
        if user.status == UserStatus.DISABLED:
            accounts.revoke_sessions(session, user)  # le saca de todos los dispositivos
        accounts.audit(session, admin, f"user.{'enabled' if body.status == 'active' else 'disabled'}", user)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _rows(session, [user])[0]


@router.post("/users/{user_id}/approve", summary="Aprobar una solicitud de registro", responses=_NOT_FOUND)
def approve_user(user_id: int, session: SessionDep, admin: AdminUser) -> AdminUserRow:
    user = _get_user(session, user_id)
    if user.status != UserStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta cuenta no está pendiente de aprobación.")
    user.status = UserStatus.ACTIVE
    accounts.audit(session, admin, "user.approved", user)
    session.add(user)
    session.commit()
    session.refresh(user)
    mailer.send_account_approved(user.email)
    return _rows(session, [user])[0]


@router.post(
    "/users/{user_id}/reject", summary="Rechazar una solicitud (borra la cuenta pendiente)", status_code=204,
    responses=_NOT_FOUND,
)  # fmt: skip
def reject_user(user_id: int, session: SessionDep, admin: AdminUser) -> Response:
    user = _get_user(session, user_id)
    if user.status != UserStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta cuenta no está pendiente de aprobación.")
    accounts.audit(session, admin, "user.rejected", user)
    accounts.delete_user(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/logout", summary="Cerrar todas sus sesiones", status_code=204, responses=_NOT_FOUND)
def logout_user(user_id: int, session: SessionDep, admin: AdminUser) -> Response:
    user = _get_user(session, user_id)
    accounts.revoke_sessions(session, user)
    accounts.audit(session, admin, "user.sessions_revoked", user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/unlock", summary="Desbloquear tras intentos fallidos", status_code=204,
             responses=_NOT_FOUND)  # fmt: skip
def unlock_user(user_id: int, session: SessionDep, admin: AdminUser) -> Response:
    user = _get_user(session, user_id)
    accounts.unlock(session, user)
    accounts.audit(session, admin, "user.unlocked", user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/users/{user_id}/reset-link",
    summary="Generar un enlace para que ponga una contraseña nueva",
    description=(
        f"Enlace de un solo uso válido {accounts.RESET_ADMIN_HOURS} h. Se devuelve para enviarlo por otro canal "
        "(WhatsApp…) y, si se pide y hay correo, también por email."
    ),
    responses=_NOT_FOUND,
)
def reset_link(user_id: int, body: ResetLinkIn, session: SessionDep, admin: AdminUser) -> LinkOut:
    user = _get_user(session, user_id)
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo para cuentas activas.")
    token, expires = accounts.create_reset(session, user, accounts.RESET_ADMIN_HOURS * 60, created_by=admin)
    emailed = body.send_email and mailer.send_password_reset(user.email, token, accounts.RESET_ADMIN_HOURS * 60)
    accounts.audit(session, admin, "user.reset_link", user, emailed=emailed)
    session.commit()
    return LinkOut(link=mailer.link(f"/restablecer?token={token}"), expires_at=expires, emailed=emailed)


@router.delete(
    "/users/{user_id}",
    summary="Borrar un usuario y todos sus datos",
    description="Irreversible. Hay que repetir su email en `confirm`. Tu propia cuenta se borra desde Ajustes.",
    status_code=204,
    responses={**_NOT_FOUND, 400: {"description": "La confirmación no coincide"}},
)
def delete_user(
    user_id: int, session: SessionDep, admin: AdminUser, confirm: Annotated[str, Query(max_length=255)]
) -> Response:
    user = _get_user(session, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tu propia cuenta se borra desde Ajustes.")
    if confirm.strip().lower() != user.email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe el email exacto del usuario para confirmar.")
    if accounts.is_last_admin(session, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Debe quedar al menos un administrador activo.")
    accounts.audit(session, admin, "user.deleted", user)
    accounts.delete_user(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Invitaciones ────────────────────────────────────────────────────────────


@router.get("/invitations", summary="Invitaciones (pendientes, usadas y caducadas)")
def list_invitations(
    session: SessionDep, _: AdminUser, limit: Annotated[int, Query(ge=1, le=200)] = 100
) -> list[InvitationRow]:
    rows = session.exec(select(Invitation).order_by(col(Invitation.created_at).desc()).limit(limit)).all()
    return [_invitation_row(session, i) for i in rows]


@router.post(
    "/invitations",
    summary="Invitar a una persona",
    description="Enlace de un solo uso. El enlace solo se devuelve ahora (en BD queda su hash).",
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Ya existe un usuario con ese email."}},
)
def create_invitation(body: InvitationIn, session: SessionDep, admin: AdminUser) -> InvitationCreated:
    email = body.email.strip().lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese email.")
    invitation = Invitation(email=email, token_hash="", created_by=admin.id, expires_at=datetime.now(UTC))
    token = _new_invitation_token(invitation, body.days)
    session.add(invitation)
    session.flush()
    emailed = body.send_email and mailer.send_invitation(email, token, invitation.expires_at)
    accounts.audit(session, admin, "invitation.created", None, email=email, days=body.days, emailed=emailed)
    session.commit()
    session.refresh(invitation)
    row = _invitation_row(session, invitation)
    return InvitationCreated(**row.model_dump(), link=mailer.link(f"/registro?token={token}"), emailed=emailed)


@router.post("/invitations/{invitation_id}/renew", summary="Renovar (enlace nuevo y nueva caducidad)",
             responses=_NOT_FOUND)  # fmt: skip
def renew_invitation(invitation_id: int, body: RenewIn, session: SessionDep, admin: AdminUser) -> InvitationCreated:
    invitation = session.get(Invitation, invitation_id)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitación no encontrada.")
    if invitation.used_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta invitación ya se usó.")
    token = _new_invitation_token(invitation, body.days)
    session.add(invitation)
    emailed = body.send_email and mailer.send_invitation(invitation.email, token, invitation.expires_at)
    accounts.audit(session, admin, "invitation.renewed", None, email=invitation.email, emailed=emailed)
    session.commit()
    session.refresh(invitation)
    row = _invitation_row(session, invitation)
    return InvitationCreated(**row.model_dump(), link=mailer.link(f"/registro?token={token}"), emailed=emailed)


@router.delete("/invitations/{invitation_id}", summary="Anular una invitación", status_code=204,
               responses=_NOT_FOUND)  # fmt: skip
def delete_invitation(invitation_id: int, session: SessionDep, admin: AdminUser) -> Response:
    invitation = session.get(Invitation, invitation_id)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitación no encontrada.")
    accounts.audit(session, admin, "invitation.deleted", None, email=invitation.email)
    session.delete(invitation)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Registro, auditoría y sistema ───────────────────────────────────────────


def _settings_out(session: Session) -> SettingsOut:
    lim = basic_limits(session)
    return SettingsOut(
        registration_mode=accounts.registration_mode(session),
        email_enabled=email_enabled(),
        captcha_enabled=captcha_enabled(),
        blocked_domains=extra_domains(session),
        limits=BasicLimitsIO(
            basic_history_days=lim.history_days,
            basic_max_goals=lim.max_goals,
            basic_max_sessions_week=lim.max_sessions_week,
        ),  # fmt: skip
    )


@router.get("/settings", summary="Ajustes del registro: modo, dominios bloqueados y límites de cuentas Básicas")
def get_app_settings(session: SessionDep, _: AdminUser) -> SettingsOut:
    return _settings_out(session)


@router.put("/settings", summary="Cambiar ajustes del registro (solo los campos enviados)")
def put_app_settings(body: SettingsIn, session: SessionDep, admin: AdminUser) -> SettingsOut:
    before = accounts.registration_mode(session)
    if body.registration_mode is not None and body.registration_mode != before:
        accounts.set_setting(session, "registration_mode", body.registration_mode)
        accounts.audit(session, admin, "settings.registration_mode", None, before=before, after=body.registration_mode)
    if body.blocked_domains is not None:
        domains = parse_domains("\n".join(body.blocked_domains))
        if domains != extra_domains(session):
            accounts.set_setting(session, "blocked_domains", ",".join(domains))
            accounts.audit(session, admin, "settings.blocked_domains", None, count=len(domains))
    if body.limits is not None:
        changed = save_basic_limits(session, **body.limits.model_dump())
        if changed:
            accounts.audit(session, admin, "settings.basic_limits", None,
                           **{k: f"{a} → {b}" for k, (a, b) in changed.items()})  # fmt: skip
    session.commit()
    return _settings_out(session)


@router.get(
    "/modules",
    summary="Valor general de los módulos",
    description="Lo que tiene cada módulo para todas las cuentas que no tengan un valor propio.",
)
def get_admin_modules(session: SessionDep, _: AdminUser) -> ModulesOut:
    return ModulesOut(**modules.all_modules(session))


@router.put(
    "/modules",
    summary="Activar o desactivar módulos de la app (solo los enviados)",
    description=(
        "Cambia el valor general de los módulos (`entrenadores`, `ia`, `reloj`, `rutas`, `nutricion`); las cuentas "
        "con un valor propio (PATCH /admin/users/{id} con `modules`) lo mantienen. Desactivar solo oculta: no "
        "borra datos. Cada cambio queda en la auditoría."
    ),
)
def put_modules(body: ModulesIn, session: SessionDep, admin: AdminUser) -> ModulesOut:
    changes = body.model_dump(exclude_none=True)
    return ModulesOut(**modules.set_modules(session, changes, admin.id))


@router.get("/audit", summary="Registro de acciones de administración (más recientes primero)")
def list_audit(
    session: SessionDep,
    _: AdminUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditRow]:
    rows = session.exec(select(AuditLog).order_by(col(AuditLog.created_at).desc(), col(AuditLog.id).desc())
                        .offset(offset).limit(limit)).all()  # fmt: skip
    return [AuditRow.model_validate(r, from_attributes=True) for r in rows]


def _heartbeat() -> datetime | None | Literal[False]:
    """Último latido del worker; False si Redis no responde."""
    try:
        value = redis.Redis.from_url(get_settings().redis_url, socket_timeout=2).get(HEARTBEAT_KEY)
    except redis.RedisError:
        return False
    return datetime.fromisoformat(value.decode()) if value else None


def _last_backup() -> dict | None:
    folder = Path(get_settings().backup_dir)
    try:
        files = sorted(folder.glob("*.sql.gz"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return None
    if not files:
        return None
    last = files[-1]
    stat = last.stat()
    return {"file": last.name, "at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            "size_mb": round(stat.st_size / 1_048_576, 1), "count": len(files)}  # fmt: skip


@router.get(
    "/system",
    summary="Estado del sistema",
    description=(
        "Sincronizador (latido de beat + worker), conexiones de Garmin caducadas, sincronizaciones con error, "
        "última copia de seguridad y correo."
    ),
)
def system(session: SessionDep, _: AdminUser) -> SystemOut:
    beat = _heartbeat()
    stale = datetime.now(UTC) - timedelta(minutes=WORKER_STALE_MIN)
    expired = session.exec(
        select(User.email).join(GarminCredential, col(GarminCredential.user_id) == col(User.id))
        .where(GarminCredential.status == "expired")
    ).all()  # fmt: skip
    latest = select(SyncRun.user_id, func.max(SyncRun.started_at).label("at")).group_by(SyncRun.user_id).subquery()
    failing = session.exec(
        select(User.email, SyncRun.started_at, SyncRun.error)
        .join(latest, (SyncRun.user_id == latest.c.user_id) & (SyncRun.started_at == latest.c.at))
        .join(User, col(User.id) == col(SyncRun.user_id))
        .where(SyncRun.status == "error")
    ).all()  # fmt: skip
    counts = dict(session.exec(select(User.status, func.count(col(User.id))).group_by(User.status)).all())
    warned = session.exec(select(User.inactivity_warned_at).where(col(User.inactivity_warned_at).is_not(None))).all()
    delete_from = datetime.now(UTC) - timedelta(days=accounts.INACTIVE_DELETE_DAYS - 7)
    return SystemOut(
        inactive_warned=len(warned),
        inactive_deleting_7d=sum(1 for w in warned if w <= delete_from),
        # None = sin datos (Redis caído o recién arrancado, aún sin latido); False = el latido se ha parado.
        worker_ok=None if not beat else beat >= stale,
        last_heartbeat=beat or None,
        last_sync_at=session.exec(select(func.max(SyncRun.finished_at))).one(),
        garmin_expired=list(expired),
        sync_failing=[{"email": e, "at": at.isoformat(), "error": err} for e, at, err in failing],
        last_backup=_last_backup(),
        email_mode=current_config(session).mode,
        users_by_status={str(k): v for k, v in counts.items()},
        pending_requests=counts.get(UserStatus.PENDING, 0),
    )


# ─── Correo (SMTP) ───────────────────────────────────────────────────────────


class EmailSettingsOut(BaseModel):
    source: Literal["panel", "env"]  # de dónde sale la configuración que se usa ahora
    mode: str  # smtp | file | disabled
    enabled: bool  # configuración del panel activada
    host: str
    port: int
    security: Literal["starttls", "ssl", "none"]
    user: str
    has_password: bool  # la contraseña nunca se devuelve
    sender: str
    public_url: str
    env_configured: bool  # hay SMTP en las variables de entorno (se usa si el panel está desactivado)


class EmailSettingsIn(BaseModel):
    enabled: bool = True
    host: str = Field(min_length=3, max_length=255, pattern=r"^[A-Za-z0-9.\-]+$")
    port: int = Field(ge=1, le=65535)
    security: Literal["starttls", "ssl", "none"] = "starttls"
    user: str = Field(default="", max_length=255)
    password: str | None = Field(default=None, max_length=500, description="None = conservar; '' = borrar")
    sender: str = Field(default="", max_length=255, description='p. ej. "KTrain <no-reply@dominio.com>"')
    public_url: str = Field(max_length=255, pattern=r"^https?://[^\s/]+(/.*)?$")


class EmailTestIn(BaseModel):
    to: str | None = Field(default=None, max_length=255, pattern=EMAIL_PATTERN)


def _email_out(session: Session) -> EmailSettingsOut:
    data = panel_config(session) or {}
    effective = current_config(session)
    s = get_settings()
    return EmailSettingsOut(
        source=effective.source,
        mode=effective.mode,
        enabled=bool(data.get("enabled")),
        host=data.get("host", s.smtp_host),
        port=int(data.get("port", s.smtp_port)),
        security=data.get(
            "security", s.smtp_security if s.smtp_security in ("starttls", "ssl", "none") else "starttls"
        ),
        user=data.get("user", s.smtp_user),
        has_password=bool(data.get("password_enc")),
        sender=data.get("sender", s.smtp_from),
        public_url=data.get("public_url") or s.app_public_url,
        env_configured=bool(s.smtp_host) or s.email_mode == "file",
    )


@router.get("/email", summary="Configuración del correo (SMTP)")
def get_email_settings(session: SessionDep, _: AdminUser) -> EmailSettingsOut:
    return _email_out(session)


@router.put(
    "/email",
    summary="Guardar la configuración del correo",
    description=(
        "Tiene prioridad sobre las variables de entorno mientras esté activada. La contraseña se guarda "
        "cifrada y no se devuelve; sin `password` se conserva la actual."
    ),
)
def put_email_settings(body: EmailSettingsIn, session: SessionDep, admin: AdminUser) -> EmailSettingsOut:
    current = panel_config(session) or {}
    data = body.model_dump(exclude={"password"})
    data["public_url"] = body.public_url.rstrip("/")
    if body.password is None:
        data["password_enc"] = current.get("password_enc")
    else:
        data["password_enc"] = encrypt_secret(body.password) if body.password else None
    accounts.set_setting(session, PANEL_KEY, json.dumps(data))
    accounts.audit(session, admin, "settings.email", None, host=body.host, enabled=body.enabled)
    session.commit()
    return _email_out(session)


@router.delete("/email", summary="Borrar la configuración del panel (vuelve a la del entorno)", status_code=204)
def delete_email_settings(session: SessionDep, admin: AdminUser) -> Response:
    row = session.get(AppSetting, PANEL_KEY)
    if row is not None:
        session.delete(row)
        accounts.audit(session, admin, "settings.email_removed", None)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/email/test",
    summary="Enviar un email de prueba con la configuración actual",
    description="Se envía en el momento (no en segundo plano) para poder mostrar el error del servidor si falla.",
    responses={400: {"description": "El envío falló (motivo en el mensaje)"}},
)
@limiter.limit("5/minute")
def test_email(request: Request, body: EmailTestIn, session: SessionDep, admin: AdminUser) -> dict:
    config = current_config(session)
    if config.mode == "disabled":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No hay correo configurado: guarda antes los datos SMTP.")
    to = body.to or admin.email
    test = Email(
        to=to,
        subject="Prueba de correo de KTrain",
        text="Si lees esto, el envío de emails de KTrain funciona.",
        html=mailer.test_html(),
    )
    try:
        send_email(test, config)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("Fallo en el email de prueba", extra={"user_id": admin.id})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, smtp_error_text(exc)) from exc
    where = "guardado en la bandeja local (modo de prueba)" if config.mode == "file" else f"enviado a {to}"
    return {"ok": True, "message": f"Email de prueba {where}."}
