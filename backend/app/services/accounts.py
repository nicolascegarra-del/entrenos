"""
Cuentas de usuario: bloqueo por intentos fallidos, cierre de sesiones, enlaces para
restablecer la contraseña, ajustes globales (modo de registro), auditoría de
administración, exportación de datos y borrado de cuenta con todos sus datos.
"""

import hashlib
import secrets
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from sqlmodel import Session, col, delete, select

from app.core.config import get_settings
from app.models import (
    AccountTier,
    Achievement,
    Activity,
    ActivityFeedback,
    ActivityReview,
    AiProviderConfig,
    AppSetting,
    AthleteZones,
    AuditLog,
    ChatConversation,
    ChatMessage,
    DailyMetric,
    Device,
    EmailVerification,
    Gear,
    Lap,
    NotificationPrefs,
    PasswordReset,
    PlannedBlock,
    PlannedSession,
    RaceGoal,
    StrengthSet,
    SyncRun,
    TrainingPlan,
    TrainingPlanWeek,
    User,
    UserProfile,
    UserStatus,
    WeightLog,
)

MIN_PASSWORD_LENGTH = 10
LOCK_THRESHOLD = 10  # fallos seguidos antes de bloquear
LOCK_MINUTES = 15
RESET_EMAIL_MINUTES = 60  # enlace pedido por la propia persona
RESET_ADMIN_HOURS = 24  # enlace generado por un administrador (se envía por otro canal)
VERIFY_HOURS = 24  # enlace para confirmar el email del autoregistro
UNVERIFIED_DELETE_HOURS = 48  # cuentas sin confirmar que se borran solas
INACTIVE_WARN_DAYS = 180  # cuentas Básicas sin entrar: aviso por email
INACTIVE_DELETE_DAYS = 30  # días tras el aviso hasta borrarlas


class RegistrationMode(StrEnum):
    INVITE = "invite"  # solo con invitación (por defecto)
    OPEN = "open"  # cualquiera puede crear su cuenta
    APPROVAL = "approval"  # cualquiera puede pedirla; un administrador la aprueba


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def now() -> datetime:
    return datetime.now(UTC)


# ─── Login y sesiones ────────────────────────────────────────────────────────


def is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > now()


def register_failed_login(session: Session, user: User) -> None:
    """Cuenta un fallo; al llegar a LOCK_THRESHOLD seguidos bloquea la cuenta LOCK_MINUTES minutos."""
    user.failed_logins += 1
    if user.failed_logins >= LOCK_THRESHOLD:
        user.locked_until = now() + timedelta(minutes=LOCK_MINUTES)
        user.failed_logins = 0
    session.add(user)
    session.commit()


def register_login(session: Session, user: User) -> None:
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now()
    user.inactivity_warned_at = None  # volver a entrar cancela el borrado por inactividad
    session.add(user)
    session.commit()


def unlock(session: Session, user: User) -> None:
    user.failed_logins, user.locked_until = 0, None
    session.add(user)


def revoke_sessions(session: Session, user: User) -> None:
    """Invalida todos los tokens emitidos hasta ahora (access y refresh) de este usuario."""
    user.token_version += 1
    session.add(user)


def admins(session: Session) -> list[User]:
    return list(session.exec(select(User).where(User.is_admin, User.status == UserStatus.ACTIVE)).all())


def is_last_admin(session: Session, user: User) -> bool:
    return user.is_admin and user.status == UserStatus.ACTIVE and len(admins(session)) <= 1


# ─── Restablecer contraseña ──────────────────────────────────────────────────


def create_reset(session: Session, user: User, minutes: int, created_by: User | None = None) -> tuple[str, datetime]:
    """
    Crea un enlace de un solo uso (anula los anteriores de ese usuario).

    Returns:
        El token en claro (solo para el enlace; en BD queda su hash) y su caducidad.
    """
    session.exec(delete(PasswordReset).where(PasswordReset.user_id == user.id, col(PasswordReset.used_at).is_(None)))
    token = secrets.token_urlsafe(32)
    expires = now() + timedelta(minutes=minutes)
    session.add(PasswordReset(user_id=user.id, token_hash=token_hash(token), expires_at=expires,
                              created_by=created_by.id if created_by else None))  # fmt: skip
    session.commit()
    return token, expires


def valid_reset(session: Session, token: str) -> PasswordReset | None:
    reset = session.exec(select(PasswordReset).where(PasswordReset.token_hash == token_hash(token))).first()
    if reset is None or reset.used_at or reset.expires_at < now():
        return None
    return reset


# ─── Confirmar email ─────────────────────────────────────────────────────────


def create_verification(session: Session, user: User) -> str:
    """Crea el enlace de confirmación (anula los anteriores). Devuelve el token en claro."""
    session.exec(delete(EmailVerification).where(EmailVerification.user_id == user.id))
    token = secrets.token_urlsafe(32)
    session.add(EmailVerification(user_id=user.id, token_hash=token_hash(token),
                                  expires_at=now() + timedelta(hours=VERIFY_HOURS)))  # fmt: skip
    session.commit()
    return token


def valid_verification(session: Session, token: str) -> EmailVerification | None:
    row = session.exec(select(EmailVerification).where(EmailVerification.token_hash == token_hash(token))).first()
    if row is None or row.used_at or row.expires_at < now():
        return None
    return row


# ─── Ajustes globales y auditoría ────────────────────────────────────────────


def get_setting(session: Session, key: str, default: str) -> str:
    row = session.get(AppSetting, key)
    return row.value if row else default


def set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(AppSetting, key) or AppSetting(key=key, value=value)
    row.value = value
    session.add(row)


def registration_mode(session: Session) -> RegistrationMode:
    value = get_setting(session, "registration_mode", RegistrationMode.INVITE)
    try:
        return RegistrationMode(value)
    except ValueError:
        return RegistrationMode.INVITE


def audit(session: Session, actor: User | None, action: str, target: User | None = None, **detail: object) -> None:
    """Anota una acción de administración (sin contraseñas ni tokens: solo datos descriptivos)."""
    session.add(AuditLog(
        actor_id=actor.id if actor else None, actor_email=actor.email if actor else None, action=action,
        target_user_id=target.id if target else None, target_email=target.email if target else None,
        detail={k: v for k, v in detail.items() if v is not None},
    ))  # fmt: skip


# ─── Exportar y borrar ───────────────────────────────────────────────────────


def _dump(rows: list, exclude: set[str] | None = None) -> list[dict]:
    return [r.model_dump(mode="json", exclude=exclude or set()) for r in rows]


def export_user_data(session: Session, user: User) -> dict:
    """
    Todos los datos de la persona en un JSON (derecho de acceso y portabilidad, RGPD).
    No incluye secretos: ni la contraseña, ni los tokens de Garmin, ni las claves de IA.
    """
    uid = user.id
    activities = session.exec(select(Activity).where(Activity.user_id == uid).order_by(Activity.start_time)).all()
    activity_ids = [a.id for a in activities]
    plans = session.exec(select(PlannedSession).where(PlannedSession.user_id == uid)).all()
    plan_ids = [p.id for p in plans]
    conversations = session.exec(select(ChatConversation).where(ChatConversation.user_id == uid)).all()
    conversation_ids = [c.id for c in conversations]
    profile = session.get(UserProfile, uid)
    training_plans = session.exec(select(TrainingPlan).where(TrainingPlan.user_id == uid)).all()
    plan_ids_tp = [p.id for p in training_plans]
    return {
        "exported_at": now().isoformat(),
        "account": {"email": user.email, "created_at": user.created_at.isoformat(), "is_admin": user.is_admin},
        "profile": profile.model_dump(mode="json") if profile else None,
        "weight_log": _dump(session.exec(select(WeightLog).where(WeightLog.user_id == uid)).all()),
        "devices": _dump(session.exec(select(Device).where(Device.user_id == uid)).all()),
        "activities": _dump(activities),
        "laps": _dump(session.exec(select(Lap).where(col(Lap.activity_id).in_(activity_ids))).all()),
        "activity_feedback": _dump(
            session.exec(select(ActivityFeedback).where(col(ActivityFeedback.activity_id).in_(activity_ids))).all()
        ),
        "strength_sets": _dump(
            session.exec(select(StrengthSet).where(col(StrengthSet.activity_id).in_(activity_ids))).all()
        ),
        "daily_metrics": _dump(session.exec(select(DailyMetric).where(DailyMetric.user_id == uid)).all()),
        "athlete_zones": _dump(session.exec(select(AthleteZones).where(AthleteZones.user_id == uid)).all()),
        "planned_sessions": _dump(plans),
        "planned_blocks": _dump(
            session.exec(select(PlannedBlock).where(col(PlannedBlock.session_id).in_(plan_ids))).all()
        ),
        "race_goals": _dump(session.exec(select(RaceGoal).where(RaceGoal.user_id == uid)).all()),
        "activity_reviews": _dump(session.exec(select(ActivityReview).where(ActivityReview.user_id == uid)).all()),
        "achievements": _dump(session.exec(select(Achievement).where(Achievement.user_id == uid)).all()),
        "gear": _dump(session.exec(select(Gear).where(Gear.user_id == uid)).all()),
        "notification_prefs": _dump(
            session.exec(select(NotificationPrefs).where(NotificationPrefs.user_id == uid)).all()
        ),
        "training_plans": _dump(training_plans),
        "training_plan_weeks": _dump(
            session.exec(select(TrainingPlanWeek).where(col(TrainingPlanWeek.plan_id).in_(plan_ids_tp))).all()
        ),
        "ai_providers": _dump(
            session.exec(select(AiProviderConfig).where(AiProviderConfig.user_id == uid)).all(), exclude={"key_enc"}
        ),
        "chat_conversations": _dump(conversations),
        "chat_messages": _dump(
            session.exec(select(ChatMessage).where(col(ChatMessage.conversation_id).in_(conversation_ids))).all()
        ),
    }


def delete_user(session: Session, user: User) -> None:
    """
    Borra a la persona y todos sus datos (y sus .FIT del almacenamiento). Las tablas sin
    borrado en cascada se vacían en orden; el resto cae con el usuario.
    """
    uid = user.id
    activity_ids = select(Activity.id).where(Activity.user_id == uid)
    session.exec(delete(RaceGoal).where(RaceGoal.user_id == uid))
    session.exec(delete(PlannedSession).where(PlannedSession.user_id == uid))
    # Laps, series, raw, sensaciones y fuerza caen en cascada con la actividad.
    session.exec(delete(Activity).where(col(Activity.id).in_(activity_ids)))
    for model in (Device, DailyMetric, AthleteZones, SyncRun):
        session.exec(delete(model).where(model.user_id == uid))
    session.delete(user)
    session.commit()
    fit_dir = Path(get_settings().storage_dir) / "fit" / str(uid)
    shutil.rmtree(fit_dir, ignore_errors=True)


# ─── Mantenimiento diario ────────────────────────────────────────────────────


def housekeeping(
    session: Session, email_on: bool, warn: Callable[[str, int], None], at: datetime | None = None
) -> dict[str, int]:
    """
    Limpieza diaria de cuentas:
    - borra las autoregistradas sin confirmar de más de UNVERIFIED_DELETE_HOURS;
    - avisa por email a las Básicas sin entrar en INACTIVE_WARN_DAYS;
    - borra las avisadas hace más de INACTIVE_DELETE_DAYS que siguen sin entrar.
    Sin correo no se avisa ni se borra por inactividad (nadie se enteraría). Completas y admins, nunca.

    Args:
        email_on: Si hay correo configurado.
        warn: Función que envía el aviso (inyectable en tests).
        at: Momento de referencia (por defecto, ahora).

    Returns:
        Recuento de cuentas borradas sin confirmar, avisadas y borradas por inactividad.
    """
    at = at or now()
    result = {"unverified_deleted": 0, "warned": 0, "inactive_deleted": 0}
    stale = session.exec(select(User).where(
        User.status == UserStatus.UNVERIFIED, User.created_at < at - timedelta(hours=UNVERIFIED_DELETE_HOURS)
    )).all()  # fmt: skip
    for user in stale:
        delete_user(session, user)
        result["unverified_deleted"] += 1
    if not email_on:
        return result
    basic = select(User).where(User.tier == AccountTier.BASIC, User.status == UserStatus.ACTIVE, ~col(User.is_admin))
    for user in session.exec(basic.where(col(User.inactivity_warned_at).is_not(None))).all():
        if user.inactivity_warned_at < at - timedelta(days=INACTIVE_DELETE_DAYS):
            audit(session, None, "user.inactive_deleted", user)
            delete_user(session, user)
            result["inactive_deleted"] += 1
    idle_since = at - timedelta(days=INACTIVE_WARN_DAYS)
    for user in session.exec(basic.where(col(User.inactivity_warned_at).is_(None))).all():
        last_seen = user.last_login_at or user.created_at
        if last_seen < idle_since:
            warn(user.email, INACTIVE_DELETE_DAYS)
            user.inactivity_warned_at = at
            session.add(user)
            result["warned"] += 1
    session.commit()
    return result
