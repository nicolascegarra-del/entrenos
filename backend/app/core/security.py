from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"
BCRYPT_ROUNDS = 12
TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int, token_type: TokenType) -> str:
    settings = get_settings()
    if token_type == "access":
        delta = timedelta(minutes=settings.jwt_access_expire_minutes)
    else:
        delta = timedelta(days=settings.jwt_refresh_expire_days)
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "type": token_type, "iat": now, "exp": now + delta}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: TokenType) -> int:
    """
    Valida firma, expiración y tipo del token.

    Returns:
        El id de usuario del token.

    Raises:
        jwt.InvalidTokenError: Si el token no es válido o no es del tipo esperado.
    """
    payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Tipo de token incorrecto")
    return int(payload["sub"])
