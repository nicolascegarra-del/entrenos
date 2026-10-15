"""
Cifrado simétrico (Fernet) de secretos guardados en la BD: tokens de Garmin y claves de
API de los asistentes de IA. La clave vive solo en variables de entorno.
"""

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        raise RuntimeError("Falta SECRETS_KEY (o GARMIN_TOKEN_KEY) para cifrar secretos.")
    return Fernet(key.encode())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value_enc: str) -> str:
    return _fernet().decrypt(value_enc.encode()).decode()
