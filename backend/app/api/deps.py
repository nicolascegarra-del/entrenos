from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.db import get_session
from app.core.security import decode_token_claims
from app.models import User, UserStatus
from app.services import modules

SessionDep = Annotated[Session, Depends(get_session)]
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado.")
    if credentials is None:
        raise unauthorized
    try:
        user_id, version = decode_token_claims(credentials.credentials, "access")
    except jwt.InvalidTokenError as exc:
        raise unauthorized from exc
    user = session.get(User, user_id)
    # Un usuario desactivado o con las sesiones cerradas (versión distinta) deja de estar autenticado.
    if user is None or user.status != UserStatus.ACTIVE or user.token_version != version:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_module(name: str) -> Callable[..., None]:
    """
    Dependencia que corta con 404 (`MODULE_DISABLED`) si el módulo está apagado para esta cuenta.

    Exige sesión antes, para que un anónimo reciba 401 y no sepa qué está activado.
    """

    def check(session: SessionDep, user: CurrentUser) -> None:
        if not modules.enabled(session, name, user):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"El módulo «{modules.LABELS[name]}» está desactivado por el administrador.",
                headers={"X-Error-Code": "MODULE_DISABLED"},
            )

    return check
