from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import ALGORITHM, create_token, decode_token, hash_password, verify_password


def test_hash_password_cuando_se_verifica_entonces_solo_acepta_la_correcta():
    hashed = hash_password("secreto-largo-1")
    assert hashed.startswith("$2b$12$")
    assert verify_password("secreto-largo-1", hashed)
    assert not verify_password("otra", hashed)


def test_decode_token_cuando_tipo_coincide_entonces_devuelve_user_id():
    assert decode_token(create_token(42, "access"), "access") == 42


def test_decode_token_cuando_se_usa_refresh_como_access_entonces_falla():
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(create_token(42, "refresh"), "access")


def test_decode_token_cuando_ha_expirado_entonces_falla():
    past = datetime.now(UTC) - timedelta(minutes=1)
    token = jwt.encode({"sub": "1", "type": "access", "exp": past}, get_settings().jwt_secret_key, ALGORITHM)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, "access")
