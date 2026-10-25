"""
Módulos de la app que el administrador activa o desactiva para todos.

Se guardan en `AppSetting` (clave `modules`, JSON con solo los valores conocidos) y se
cachean ~30 s en Redis para no ir a la BD en cada petición; guardar invalida la caché.
Si Redis falla se lee de la BD. Desactivar un módulo solo lo oculta: nunca borra datos.
"""

import contextlib
import hashlib
import json
import logging

import redis
from sqlmodel import Session

from app.core.config import get_settings
from app.models import User
from app.services import accounts

logger = logging.getLogger(__name__)

SETTING_KEY = "modules"
CACHE_SECONDS = 30

# Orden = orden en el panel. Valor = activado por defecto.
DEFAULTS: dict[str, bool] = {
    "entrenadores": False,
    "ia": True,
    "reloj": True,
    "rutas": True,
    "nutricion": False,
}
LABELS: dict[str, str] = {
    "entrenadores": "Entrenadores",
    "ia": "Entrenador IA",
    "reloj": "Envío al reloj",
    "rutas": "Rutas",
    "nutricion": "Nutrición",
}


def _cache_key() -> str:
    # La BD forma parte de la clave: dos entornos (o los tests) que compartan Redis no se pisan.
    db = hashlib.sha256(get_settings().database_url.encode()).hexdigest()[:12]
    return f"app-modules:{db}"


def _redis() -> redis.Redis | None:
    try:
        return redis.Redis.from_url(get_settings().redis_url, socket_timeout=2, decode_responses=True)
    except redis.RedisError:
        return None


def _parse(raw: str | None) -> dict[str, bool]:
    """Valores por defecto + lo guardado (ignora claves desconocidas o JSON roto)."""
    out = dict(DEFAULTS)
    if not raw:
        return out
    try:
        stored = json.loads(raw)
    except ValueError:
        return out
    if isinstance(stored, dict):
        out.update({k: bool(v) for k, v in stored.items() if k in DEFAULTS})
    return out


def _from_db(session: Session) -> dict[str, bool]:
    return _parse(accounts.get_setting(session, SETTING_KEY, ""))


def all_modules(session: Session) -> dict[str, bool]:
    """Estado de todos los módulos (caché de Redis; si no responde, la BD)."""
    cache = _redis()
    if cache is not None:
        try:
            cached = cache.get(_cache_key())
            if cached is not None:
                return _parse(cached)
        except redis.RedisError:
            cache = None
    values = _from_db(session)
    if cache is not None:
        with contextlib.suppress(redis.RedisError):
            cache.setex(_cache_key(), CACHE_SECONDS, json.dumps(values))
    return values


def enabled(session: Session, name: str) -> bool:
    """¿Está activado el módulo `name`? Un nombre desconocido cuenta como desactivado."""
    return all_modules(session).get(name, False)


def invalidate_cache() -> None:
    cache = _redis()
    if cache is not None:
        with contextlib.suppress(redis.RedisError):
            cache.delete(_cache_key())


def set_modules(session: Session, changes: dict[str, bool], admin_id: int | None) -> dict[str, bool]:
    """
    Aplica los cambios (solo las claves enviadas), los anota en la auditoría y guarda.

    Raises:
        ValueError: Si algún nombre de módulo no existe.
    """
    unknown = sorted(set(changes) - set(DEFAULTS))
    if unknown:
        raise ValueError(f"Módulo desconocido: {', '.join(unknown)}.")
    before = _from_db(session)
    after = {**before, **{k: bool(v) for k, v in changes.items()}}
    diff = {k: after[k] for k in DEFAULTS if after[k] != before[k]}
    if diff:
        accounts.set_setting(session, SETTING_KEY, json.dumps(after))
        admin = session.get(User, admin_id) if admin_id is not None else None
        accounts.audit(session, admin, "settings.modules", None,
                       **{k: "activado" if v else "desactivado" for k, v in diff.items()})  # fmt: skip
        session.commit()
        logger.info("Módulos cambiados: %s", diff)
    # Tras el commit: así nadie vuelve a cachear el valor viejo.
    invalidate_cache()
    return after
