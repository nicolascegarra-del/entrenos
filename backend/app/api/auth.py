from dataclasses import asdict
from typing import Annotated, Literal

import jwt
from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.email import email_enabled
from app.core.rate_limit import limiter
from app.core.security import create_token, decode_token_claims, hash_password, verify_password
from app.models import AccountTier, User, UserStatus
from app.schemas.auth import EMAIL_PATTERN, LimitsRead, LoginRequest, TokenResponse, UserRead
from app.services import accounts, mailer
from app.services.limits import basic_limits, limits_for
from app.services.signup_guard import captcha_enabled, is_blocked_email, verify_captcha

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
_ERRORS = {401: {"description": "Credenciales o refresh token no válidos."}}
Password = Annotated[str, Field(min_length=accounts.MIN_PASSWORD_LENGTH, max_length=128)]


def _token_response(response: Response, user: User) -> TokenResponse:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        create_token(user.id, "refresh", user.token_version),
        max_age=settings.jwt_refresh_expire_days * 86400,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/api/v1/auth",
    )
    return TokenResponse(
        access_token=create_token(user.id, "access", user.token_version),
        expires_in=settings.jwt_access_expire_minutes * 60,
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


def _normalize(email: str) -> str:
    return email.strip().lower()


class OptionsOut(BaseModel):
    registration: accounts.RegistrationMode
    email_enabled: bool
    # El autoregistro exige confirmar el email: sin correo configurado solo hay invitaciones.
    signup_available: bool
    captcha_site_key: str | None
    basic_history_days: int  # para explicar los límites de las cuentas Básicas antes de registrarse


class SignupIn(BaseModel):
    email: str = Field(max_length=255, pattern=EMAIL_PATTERN)
    password: Password
    captcha_token: str | None = Field(default=None, max_length=4096)


class SignupOut(BaseModel):
    status: Literal["unverified"]
    message: str


class VerifyIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)


class VerifyOut(BaseModel):
    status: Literal["active", "pending"]
    access_token: str | None = None
    expires_in: int | None = None


class ResendIn(BaseModel):
    email: str = Field(max_length=255, pattern=EMAIL_PATTERN)


class ForgotIn(BaseModel):
    email: str = Field(max_length=255, pattern=EMAIL_PATTERN)


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    password: Password


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)


@router.post(
    "/login",
    summary="Iniciar sesión",
    description=(
        "Devuelve un access token (guárdalo en memoria) y fija el refresh token en cookie HttpOnly. Tras "
        f"{accounts.LOCK_THRESHOLD} fallos seguidos la cuenta se bloquea {accounts.LOCK_MINUTES} minutos."
    ),
    responses={
        **_ERRORS,
        403: {"description": "Cuenta desactivada o pendiente de aprobación."},
        423: {"description": "Cuenta bloqueada temporalmente por intentos fallidos."},
        429: {"description": "Demasiados intentos."},
    },
)
@limiter.limit("5/minute")
def login(request: Request, response: Response, body: LoginRequest, session: SessionDep) -> TokenResponse:
    user = session.exec(select(User).where(User.email == body.email)).first()
    if user is not None and accounts.is_locked(user):
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Cuenta bloqueada por demasiados intentos fallidos. Prueba en {accounts.LOCK_MINUTES} minutos o "
            "restablece tu contraseña.",
        )
    if user is None or not verify_password(body.password, user.password_hash):
        if user is not None:
            accounts.register_failed_login(session, user)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña incorrectos.")
    if user.status == UserStatus.UNVERIFIED:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Confirma tu email: te enviamos un enlace al registrarte.",
            headers={"X-Error-Code": "EMAIL_NOT_VERIFIED"},
        )
    if user.status == UserStatus.PENDING:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Tu solicitud está pendiente de que un administrador la apruebe."
        )
    if user.status == UserStatus.DISABLED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu cuenta está desactivada. Contacta con el administrador.")
    accounts.register_login(session, user)
    return _token_response(response, user)


@router.post(
    "/refresh",
    summary="Renovar access token",
    description="Usa la cookie de refresh para emitir un access token nuevo y rotar la cookie.",
    responses=_ERRORS,
)
@limiter.limit("30/minute")
def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión caducada.")
    if not refresh_token:
        raise unauthorized
    try:
        user_id, version = decode_token_claims(refresh_token, "refresh")
    except jwt.InvalidTokenError as exc:
        raise unauthorized from exc
    user = session.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE or user.token_version != version:
        raise unauthorized
    return _token_response(response, user)


@router.post("/logout", summary="Cerrar sesión", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    _clear_cookie(response)


@router.post(
    "/logout-all",
    summary="Cerrar sesión en todos los dispositivos",
    description="Invalida todos los tokens del usuario, también los de este dispositivo.",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout_all(response: Response, session: SessionDep, user: CurrentUser) -> None:
    accounts.revoke_sessions(session, user)
    session.commit()
    _clear_cookie(response)


@router.get("/me", summary="Usuario actual", responses=_ERRORS)
def me(session: SessionDep, user: CurrentUser) -> UserRead:
    limits = limits_for(session, user)
    return UserRead(id=user.id, email=user.email, is_admin=user.is_admin, tier=user.tier,
                    onboarded=user.onboarded_at is not None,
                    limits=LimitsRead(**asdict(limits)))  # fmt: skip


class OnboardingIn(BaseModel):
    done: bool


@router.put(
    "/me/onboarding",
    summary="Marcar la configuración guiada como hecha (o volver a mostrarla)",
    description="`done: true` al terminarla u omitirla; `done: false` para repetirla desde Ajustes.",
    status_code=status.HTTP_204_NO_CONTENT,
)
def set_onboarding(body: OnboardingIn, session: SessionDep, user: CurrentUser) -> None:
    user.onboarded_at = accounts.now() if body.done else None
    session.add(user)
    session.commit()


# ─── Registro y recuperación (públicos) ──────────────────────────────────────


@router.get("/options", summary="Opciones públicas del login y del registro")
def options(session: SessionDep) -> OptionsOut:
    mode = accounts.registration_mode(session)
    return OptionsOut(
        registration=mode,
        email_enabled=email_enabled(),
        signup_available=mode != accounts.RegistrationMode.INVITE and email_enabled(),
        captcha_site_key=get_settings().turnstile_site_key if captcha_enabled() else None,
        basic_history_days=basic_limits(session).history_days,
    )


@router.post(
    "/signup",
    summary="Crear cuenta sin invitación (registro abierto o con aprobación)",
    description=(
        "Crea una cuenta Básica sin confirmar y envía un enlace para confirmar el email. Exige correo "
        "configurado, captcha (si está activado) y un email no desechable."
    ),
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"description": "Captcha no superado"},
        403: {"description": "El registro es solo con invitación o no hay correo configurado"},
        409: {"description": "Email en uso"},
        422: {"description": "Email desechable o datos no válidos"},
    },
)
@limiter.limit("5/minute")
def signup(request: Request, body: SignupIn, session: SessionDep) -> SignupOut:
    mode = accounts.registration_mode(session)
    if mode == accounts.RegistrationMode.INVITE or not email_enabled():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El registro es solo con invitación de un administrador.")
    if not verify_captcha(body.captcha_token, request.client.host if request.client else None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No hemos podido comprobar que no eres un robot. Reinténtalo.")
    email = _normalize(body.email)
    if is_blocked_email(session, email):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Usa un email permanente: no se admiten emails temporales."
        )
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese email.")
    user = User(email=email, password_hash=hash_password(body.password), status=UserStatus.UNVERIFIED,
                tier=AccountTier.BASIC)  # fmt: skip
    session.add(user)
    session.commit()
    session.refresh(user)
    mailer.send_email_verification(email, accounts.create_verification(session, user), accounts.VERIFY_HOURS)
    return SignupOut(
        status="unverified", message=f"Te hemos enviado un email a {email}. Abre el enlace para confirmar tu cuenta."
    )


@router.post(
    "/verify",
    summary="Confirmar el email con el enlace",
    description=(
        "Registro abierto: activa la cuenta e inicia sesión (`active`). Con aprobación: la deja pendiente y avisa "
        "a los administradores (`pending`)."
    ),
    responses={400: {"description": "Enlace no válido o caducado"}},
)
@limiter.limit("10/minute")
def verify_email(request: Request, response: Response, body: VerifyIn, session: SessionDep) -> VerifyOut:
    row = accounts.valid_verification(session, body.token)
    user = session.get(User, row.user_id) if row else None
    if row is None or user is None or user.status != UserStatus.UNVERIFIED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El enlace no es válido o ha caducado. Pide uno nuevo.")
    row.used_at = accounts.now()
    session.add(row)
    if accounts.registration_mode(session) == accounts.RegistrationMode.APPROVAL:
        user.status = UserStatus.PENDING
        session.add(user)
        session.commit()
        mailer.send_approval_request([a.email for a in accounts.admins(session)], user.email)
        return VerifyOut(status="pending")
    user.status = UserStatus.ACTIVE
    session.add(user)
    session.commit()
    accounts.register_login(session, user)
    tokens = _token_response(response, user)
    return VerifyOut(status="active", access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post(
    "/verify/resend",
    summary="Reenviar el email de confirmación",
    description="Responde siempre 202 (no revela si el email existe).",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("3/minute")
def resend_verification(request: Request, body: ResendIn, session: SessionDep) -> dict:
    user = session.exec(select(User).where(User.email == _normalize(body.email))).first()
    if user is not None and user.status == UserStatus.UNVERIFIED:
        mailer.send_email_verification(user.email, accounts.create_verification(session, user), accounts.VERIFY_HOURS)
    return {"message": "Si la cuenta está pendiente de confirmar, te hemos enviado un enlace nuevo."}


@router.post(
    "/forgot",
    summary="Pedir un enlace para restablecer la contraseña",
    description=(
        "Responde siempre 202 (no revela si el email existe). Si existe una cuenta activa y hay correo "
        f"configurado, envía un enlace válido {accounts.RESET_EMAIL_MINUTES} minutos."
    ),
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("3/minute")
def forgot(request: Request, body: ForgotIn, session: SessionDep) -> dict:
    user = session.exec(select(User).where(User.email == _normalize(body.email))).first()
    if user is not None and user.status == UserStatus.ACTIVE and email_enabled():
        token, _ = accounts.create_reset(session, user, accounts.RESET_EMAIL_MINUTES)
        mailer.send_password_reset(user.email, token, accounts.RESET_EMAIL_MINUTES)
    return {"message": "Si el email tiene cuenta, te hemos enviado un enlace para restablecer la contraseña."}


@router.get("/reset/check", summary="Comprobar un enlace de restablecimiento (público)")
@limiter.limit("20/minute")
def check_reset(request: Request, token: str, session: SessionDep) -> dict:
    reset = accounts.valid_reset(session, token)
    if reset is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El enlace no es válido o ha caducado. Pide uno nuevo.")
    return {"email": session.get(User, reset.user_id).email}


@router.post(
    "/reset",
    summary="Poner una contraseña nueva con el enlace",
    description="Cierra todas las sesiones abiertas y desbloquea la cuenta.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"description": "Enlace no válido o caducado"}},
)
@limiter.limit("5/minute")
def reset_password(request: Request, body: ResetIn, session: SessionDep) -> None:
    reset = accounts.valid_reset(session, body.token)
    if reset is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El enlace no es válido o ha caducado. Pide uno nuevo.")
    user = session.get(User, reset.user_id)
    user.password_hash = hash_password(body.password)
    accounts.unlock(session, user)
    accounts.revoke_sessions(session, user)
    reset.used_at = accounts.now()
    session.add(reset)
    session.commit()


# ─── Mi cuenta ───────────────────────────────────────────────────────────────


@router.post(
    "/password",
    summary="Cambiar mi contraseña",
    description="Cierra las sesiones de los demás dispositivos; este sigue con tokens nuevos.",
    responses={400: {"description": "La contraseña actual no es correcta"}},
)
@limiter.limit("5/minute")
def change_password(
    request: Request, response: Response, body: PasswordChangeIn, session: SessionDep, user: CurrentUser
) -> TokenResponse:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña actual no es correcta.")
    user.password_hash = hash_password(body.new_password)
    accounts.revoke_sessions(session, user)
    session.commit()
    session.refresh(user)
    return _token_response(response, user)


@router.get(
    "/me/export",
    summary="Descargar todos mis datos (JSON)",
    description="Perfil, actividades, plan, objetivos, conversaciones… Sin contraseñas, tokens ni claves de IA.",
)
@limiter.limit("5/minute")
def export_me(request: Request, session: SessionDep, user: CurrentUser) -> JSONResponse:
    filename = f"entrenos-mis-datos-{accounts.now():%Y%m%d}.json"
    return JSONResponse(
        accounts.export_user_data(session, user),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/me",
    summary="Borrar mi cuenta y todos mis datos",
    description="Irreversible. Pide la contraseña. El último administrador no puede borrarse si hay más usuarios.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"description": "Contraseña incorrecta"}, 409: {"description": "Último administrador"}},
)
@limiter.limit("3/minute")
def delete_me(
    request: Request, response: Response, body: DeleteAccountIn, session: SessionDep, user: CurrentUser
) -> None:
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña no es correcta.")
    others = session.exec(select(User).where(User.id != user.id)).first()
    if others is not None and accounts.is_last_admin(session, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Eres el único administrador: nombra antes a otro desde Admin.")
    accounts.audit(session, user, "account.self_deleted", user)
    accounts.delete_user(session, user)
    _clear_cookie(response)
