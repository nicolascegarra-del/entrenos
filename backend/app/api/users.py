"""Alta de usuarios por invitación (enlaces públicos). La gestión está en `app/api/admin.py`."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.auth import _token_response
from app.api.deps import CurrentUser, SessionDep
from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.models import Invitation, User
from app.schemas.auth import TokenResponse
from app.services import accounts

router = APIRouter(tags=["usuarios"])


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo un administrador puede hacer esto.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


class RegisterIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    password: str = Field(min_length=accounts.MIN_PASSWORD_LENGTH, max_length=128)


def valid_invitation(session: Session, token: str) -> Invitation:
    invitation = session.exec(select(Invitation).where(Invitation.token_hash == accounts.token_hash(token))).first()
    if invitation is None or invitation.used_at or invitation.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La invitación no es válida o ha caducado.")
    return invitation


@router.get("/invitations/check", summary="Comprobar una invitación (público)")
@limiter.limit("20/minute")
def check_invitation(request: Request, token: str, session: SessionDep) -> dict:
    return {"email": valid_invitation(session, token).email}


@router.post(
    "/auth/register",
    summary="Crear usuario con una invitación (público)",
    description="Crea el usuario con el email de la invitación, la marca como usada e inicia sesión.",
    responses={400: {"description": "Invitación no válida o caducada."}},
)
@limiter.limit("5/minute")
def register(request: Request, response: Response, body: RegisterIn, session: SessionDep) -> TokenResponse:
    invitation = valid_invitation(session, body.token)
    if session.exec(select(User).where(User.email == invitation.email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese email.")
    user = User(email=invitation.email, password_hash=hash_password(body.password))
    session.add(user)
    session.flush()
    invitation.used_at, invitation.used_by = datetime.now(UTC), user.id
    session.add(invitation)
    session.commit()
    session.refresh(user)
    accounts.register_login(session, user)
    return _token_response(response, user)
