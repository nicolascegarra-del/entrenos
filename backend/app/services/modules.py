"""
Módulos de la app que el administrador activa o desactiva: un valor general para todos y, si quiere,
otro distinto para cada cuenta (`User.module_overrides`, que manda sobre el general).

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
    "oura": True,
    "suunto": True,
    "zepp": True,
    "xiaomi": True,
    "samsung": True,
}
LABELS: dict[str, str] = {
    "entrenadores": "Entrenadores",
    "ia": "Entrenador IA",
    "reloj": "Envío al reloj",
    "rutas": "Rutas",
    "nutricion": "Nutrición",
    "oura": "Oura Ring",
    "suunto": "Suunto",
    "zepp": "Amazfit (Zepp)",
    "xiaomi": "Xiaomi (Mi Fitness)",
    "samsung": "Samsung Health",
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


def clean_overrides(raw: object) -> dict[str, bool]:
    """Solo los módulos conocidos con valor booleano (lo demás se ignora)."""
    if not isinstance(raw, dict):
        return {}
    return {k: bool(v) for k, v in raw.items() if k in DEFAULTS and v is not None}


def for_user(session: Session, user: User | int | None) -> dict[str, bool]:
    """Módulos de una cuenta: el valor general con lo que el administrador haya fijado para ella encima."""
    values = all_modules(session)
    if user is None:
        return values
    row = session.get(User, user) if isinstance(user, int) else user
    if row is not None:
        values = {**values, **clean_overrides(row.module_overrides)}
    return values


def enabled(session: Session, name: str, user: User | int | None = None) -> bool:
    """
    ¿Está activado el módulo `name`? Con `user`, para esa cuenta; sin él, el valor general.
    Un nombre desconocido cuenta como desactivado.
    """
    return for_user(session, user).get(name, False)


def set_user_modules(session: Session, user: User, changes: dict[str, bool | None], admin: User | None) -> dict:
    """
    Fija (True/False) o devuelve al valor general (None) módulos de una cuenta y lo anota en la auditoría.

    Raises:
        ValueError: Si algún nombre de módulo no existe.
    """
    unknown = sorted(set(changes) - set(DEFAULTS))
    if unknown:
        raise ValueError(f"Módulo desconocido: {', '.join(unknown)}.")
    current = clean_overrides(user.module_overrides)
    after = dict(current)
    for k, v in changes.items():
        if v is None:
            after.pop(k, None)
        else:
            after[k] = bool(v)
    if after != current:
        user.module_overrides = after
        session.add(user)
        diff = {k: ("general" if k not in after else "activado" if after[k] else "desactivado")
                for k in DEFAULTS if current.get(k) != after.get(k)}  # fmt: skip
        accounts.audit(session, admin, "user.modules", user, **diff)
        session.commit()
    return after


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
