"""Alta de usuarios por invitación (cada persona con su usuario y su propio Garmin)."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.api.auth import _token_response
from app.api.deps import CurrentUser, SessionDep
from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.models import GarminCredential, Invitation, User
from app.schemas.auth import EMAIL_PATTERN, TokenResponse

router = APIRouter(tags=["usuarios"])

INVITATION_DAYS = 7
MIN_PASSWORD_LENGTH = 10


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo un administrador puede hacer esto.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


class UserRow(BaseModel):
    id: int
    email: str
    is_admin: bool
    created_at: datetime
    garmin: str  # none | ok | expired


class InvitationIn(BaseModel):
    email: str = Field(max_length=255, pattern=EMAIL_PATTERN)


class InvitationOut(BaseModel):
    id: int
    email: str
    expires_at: datetime
    token: str | None = None  # solo al crearla: después no se puede recuperar


class RegisterIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


def _valid_invitation(session: SessionDep, token: str) -> Invitation:
    invitation = session.exec(select(Invitation).where(Invitation.token_hash == _hash(token))).first()
    if invitation is None or invitation.used_at or invitation.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La invitación no es válida o ha caducado.")
    return invitation


@router.get("/users", summary="Usuarios de la app (solo administrador)")
def list_users(session: SessionDep, _: AdminUser) -> list[UserRow]:
    users = session.exec(select(User).order_by(User.id)).all()
    credentials = {c.user_id: c.status for c in session.exec(select(GarminCredential)).all()}
    return [
        UserRow(
            id=u.id, email=u.email, is_admin=u.is_admin, created_at=u.created_at, garmin=credentials.get(u.id, "none")
        )  # fmt: skip
        for u in users
    ]


@router.get("/invitations", summary="Invitaciones pendientes (solo administrador)")
def list_invitations(session: SessionDep, _: AdminUser) -> list[InvitationOut]:
    rows = session.exec(
        select(Invitation)
        .where(col(Invitation.used_at).is_(None), Invitation.expires_at > datetime.now(UTC))
        .order_by(col(Invitation.created_at).desc())
    ).all()
    return [InvitationOut(id=i.id, email=i.email, expires_at=i.expires_at) for i in rows]


@router.post(
    "/invitations",
    summary="Invitar a una persona",
    description=f"Crea un enlace de un solo uso válido {INVITATION_DAYS} días. El token solo se devuelve ahora.",
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Ya existe un usuario con ese email."}},
)
def create_invitation(body: InvitationIn, session: SessionDep, admin: AdminUser) -> InvitationOut:
    email = body.email.strip().lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese email.")
    token = secrets.token_urlsafe(32)
    invitation = Invitation(email=email, token_hash=_hash(token), created_by=admin.id,
                            expires_at=datetime.now(UTC) + timedelta(days=INVITATION_DAYS))  # fmt: skip
    session.add(invitation)
    session.commit()
    session.refresh(invitation)
    return InvitationOut(id=invitation.id, email=email, expires_at=invitation.expires_at, token=token)


@router.delete("/invitations/{invitation_id}", summary="Anular una invitación", status_code=204)
def delete_invitation(invitation_id: int, session: SessionDep, _: AdminUser) -> Response:
    invitation = session.get(Invitation, invitation_id)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitación no encontrada.")
    session.delete(invitation)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/invitations/check", summary="Comprobar una invitación (público)")
@limiter.limit("20/minute")
def check_invitation(request: Request, token: str, session: SessionDep) -> dict:
    return {"email": _valid_invitation(session, token).email}


@router.post(
    "/auth/register",
    summary="Crear usuario con una invitación (público)",
    description="Crea el usuario con el email de la invitación, la marca como usada e inicia sesión.",
    responses={400: {"description": "Invitación no válida o caducada."}},
)
@limiter.limit("5/minute")
def register(request: Request, response: Response, body: RegisterIn, session: SessionDep) -> TokenResponse:
    invitation = _valid_invitation(session, body.token)
    if session.exec(select(User).where(User.email == invitation.email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese email.")
    user = User(email=invitation.email, password_hash=hash_password(body.password))
    session.add(user)
    invitation.used_at = datetime.now(UTC)
    session.add(invitation)
    session.commit()
    session.refresh(user)
    return _token_response(response, user.id)
