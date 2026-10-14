from typing import Annotated

import jwt
from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import create_token, decode_token, verify_password
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
_ERRORS = {401: {"description": "Credenciales o refresh token no válidos."}}


def _token_response(response: Response, user_id: int) -> TokenResponse:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        create_token(user_id, "refresh"),
        max_age=settings.jwt_refresh_expire_days * 86400,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/api/v1/auth",
    )
    return TokenResponse(
        access_token=create_token(user_id, "access"),
        expires_in=settings.jwt_access_expire_minutes * 60,
    )


@router.post(
    "/login",
    summary="Iniciar sesión",
    description="Devuelve un access token (guárdalo en memoria) y fija el refresh token en cookie HttpOnly.",
    responses={**_ERRORS, 429: {"description": "Demasiados intentos."}},
)
@limiter.limit("5/minute")
def login(request: Request, response: Response, body: LoginRequest, session: SessionDep) -> TokenResponse:
    user = session.exec(select(User).where(User.email == body.email)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña incorrectos.")
    return _token_response(response, user.id)


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
        user_id = decode_token(refresh_token, "refresh")
    except jwt.InvalidTokenError as exc:
        raise unauthorized from exc
    if session.get(User, user_id) is None:
        raise unauthorized
    return _token_response(response, user_id)


@router.post("/logout", summary="Cerrar sesión", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


@router.get("/me", summary="Usuario actual", responses=_ERRORS)
def me(user: CurrentUser) -> UserRead:
    return UserRead(id=user.id, email=user.email)
